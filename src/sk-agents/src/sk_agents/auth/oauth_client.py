"""
OAuth 2.1 Client Implementation

Main OAuth client for handling authorization code flow with PKCE.
Implements MCP specification requirements for OAuth authorization.

Key Features:
- Authorization URL generation with PKCE + resource parameter
- Authorization code exchange for access token
- Token refresh with rotation
- Resource-bound token acquisition

References:
- MCP Specification 2025-06-18
- OAuth 2.1 Draft
- RFC 8707 (Resource Indicators)
"""

import logging
from typing import Any
from urllib.parse import urlencode

import httpx
from ska_utils import AppConfig

from sk_agents.auth.oauth_models import (
    AuthorizationRequest,
    RefreshTokenRequest,
    TokenRequest,
    TokenResponse,
)
from sk_agents.auth.oauth_pkce import PKCEManager
from sk_agents.auth.oauth_state_manager import OAuthStateManager
from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.models import OAuth2AuthData

logger = logging.getLogger(__name__)


class OAuthClient:
    """
    OAuth 2.1 Client for MCP Server Authentication.

    Handles complete OAuth authorization code flow with PKCE and resource binding.
    """

    def __init__(self, timeout: float = 30.0):
        """
        Initialize OAuth client.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self.pkce_manager = PKCEManager()
        self.state_manager = OAuthStateManager()
        self.auth_storage_factory = AuthStorageFactory(AppConfig())
        self.auth_storage = self.auth_storage_factory.get_auth_storage_manager()

    def build_authorization_url(self, request: AuthorizationRequest) -> str:
        """
        Build complete OAuth authorization URL.

        Constructs URL with all required parameters:
        - response_type=code
        - client_id, redirect_uri
        - resource (canonical MCP server URI)
        - code_challenge, code_challenge_method=S256
        - scope, state

        Args:
            request: Authorization request parameters

        Returns:
            str: Complete authorization URL for user redirect
        """
        params = {
            "response_type": request.response_type,
            "client_id": request.client_id,
            "redirect_uri": str(request.redirect_uri),
            "resource": request.resource,
            "scope": " ".join(request.scopes),
            "state": request.state,
            "code_challenge": request.code_challenge,
            "code_challenge_method": request.code_challenge_method,
        }

        # Build URL
        base_url = str(request.auth_server).rstrip("/")
        # Append /authorize if not already in URL
        if not base_url.endswith("/authorize"):
            base_url = f"{base_url}/authorize"

        auth_url = f"{base_url}?{urlencode(params)}"
        logger.debug(f"Built authorization URL for resource={request.resource}")
        return auth_url

    async def exchange_code_for_tokens(self, token_request: TokenRequest) -> TokenResponse:
        """
        Exchange authorization code for access token.

        Makes POST request to token endpoint with:
        - grant_type=authorization_code
        - code, redirect_uri
        - code_verifier (PKCE)
        - resource (canonical URI)
        - client_id (+ client_secret if confidential)

        Args:
            token_request: Token request parameters

        Returns:
            TokenResponse: Access token and metadata

        Raises:
            httpx.HTTPError: If token request fails
            ValueError: If response is invalid
        """
        # Build request body
        body = {
            "grant_type": token_request.grant_type,
            "client_id": token_request.client_id,
            "resource": token_request.resource,
        }

        # Add grant-specific parameters
        if token_request.grant_type == "authorization_code":
            if not token_request.code or not token_request.redirect_uri or not token_request.code_verifier:
                raise ValueError("Missing required parameters for authorization_code grant")
            body["code"] = token_request.code
            body["redirect_uri"] = str(token_request.redirect_uri)
            body["code_verifier"] = token_request.code_verifier
        elif token_request.grant_type == "refresh_token":
            if not token_request.refresh_token:
                raise ValueError("Missing refresh_token for refresh_token grant")
            body["refresh_token"] = token_request.refresh_token

        # Add client secret if provided (confidential client)
        if token_request.client_secret:
            body["client_secret"] = token_request.client_secret

        logger.debug(f"Exchanging code for tokens: endpoint={token_request.token_endpoint}, grant_type={token_request.grant_type}")

        # Make token request
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                str(token_request.token_endpoint),
                data=body,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

            if response.status_code != 200:
                error_data = response.json() if response.headers.get("content-type") == "application/json" else {}
                logger.error(
                    f"Token request failed: status={response.status_code}, error={error_data}"
                )
                raise httpx.HTTPError(
                    f"Token request failed: {error_data.get('error', 'unknown_error')}"
                )

            # Parse response
            token_data = response.json()
            token_response = TokenResponse(**token_data)
            logger.info(f"Successfully obtained access token for resource={token_request.resource}")
            return token_response

    async def refresh_access_token(self, refresh_request: RefreshTokenRequest) -> TokenResponse:
        """
        Refresh expired access token.

        Makes POST request to token endpoint with:
        - grant_type=refresh_token
        - refresh_token
        - resource (must match original)
        - client_id

        Implements token rotation per OAuth 2.1.

        Args:
            refresh_request: Refresh token request parameters

        Returns:
            TokenResponse: New access token (and possibly new refresh token)

        Raises:
            httpx.HTTPError: If refresh fails
        """
        token_request = TokenRequest(
            token_endpoint=refresh_request.token_endpoint,
            grant_type="refresh_token",
            refresh_token=refresh_request.refresh_token,
            resource=refresh_request.resource,
            client_id=refresh_request.client_id,
            client_secret=refresh_request.client_secret,
        )

        logger.debug(f"Refreshing access token for resource={refresh_request.resource}")
        return await self.exchange_code_for_tokens(token_request)

    async def initiate_authorization_flow(
        self,
        server_config: "McpServerConfig",
        user_id: str,
    ) -> str:
        """
        Initiate OAuth authorization flow for MCP server.

        Generates PKCE pair, state, stores flow state, and returns authorization URL.

        Args:
            server_config: MCP server configuration
            user_id: User ID initiating the flow

        Returns:
            str: Authorization URL for user redirect

        Raises:
            ValueError: If server configuration is invalid
        """
        from datetime import datetime, timezone
        from sk_agents.configs import TA_OAUTH_CLIENT_NAME
        from ska_utils import AppConfig

        # Get canonical resource URI
        try:
            resource = server_config.effective_canonical_uri
        except ValueError as e:
            logger.error(f"Cannot determine canonical URI for {server_config.name}: {e}")
            raise

        # Generate PKCE pair
        verifier, challenge = self.pkce_manager.generate_pkce_pair()

        # Generate state
        state = self.state_manager.generate_state()

        # Store flow state
        self.state_manager.store_flow_state(
            state=state,
            verifier=verifier,
            user_id=user_id,
            server_name=server_config.name,
            resource=resource,
            scopes=server_config.scopes,
        )

        # Get client configuration
        app_config = AppConfig()
        client_name = app_config.get(TA_OAUTH_CLIENT_NAME.env_name)

        # Build authorization request
        auth_request = AuthorizationRequest(
            auth_server=server_config.auth_server,
            client_id=server_config.oauth_client_id or client_name,
            redirect_uri=server_config.oauth_redirect_uri,
            resource=resource,
            scopes=server_config.scopes,
            state=state,
            code_challenge=challenge,
            code_challenge_method="S256",
        )

        # Build and return authorization URL
        auth_url = self.build_authorization_url(auth_request)
        logger.info(
            f"Initiated OAuth flow for {server_config.name}: "
            f"user={user_id}, resource={resource}, state={state}"
        )
        return auth_url

    async def handle_callback(
        self,
        code: str,
        state: str,
        user_id: str,
        server_config: "McpServerConfig",
    ) -> OAuth2AuthData:
        """
        Handle OAuth callback after user authorization.

        Validates state, exchanges code for tokens, and stores in AuthStorage.

        Args:
            code: Authorization code from callback
            state: State parameter from callback
            user_id: User ID to validate against
            server_config: MCP server configuration

        Returns:
            OAuth2AuthData: Stored token data

        Raises:
            ValueError: If state invalid or user mismatch
            httpx.HTTPError: If token exchange fails
        """
        from datetime import datetime, timedelta, timezone
        from sk_agents.mcp_client import build_auth_storage_key
        from sk_agents.configs import TA_OAUTH_CLIENT_NAME
        from ska_utils import AppConfig

        # Retrieve and validate flow state
        flow_state = self.state_manager.retrieve_flow_state(state, user_id)

        # Get token endpoint (from server metadata or construct from auth_server)
        token_endpoint = f"{server_config.auth_server.rstrip('/')}/token"

        # Get client configuration
        app_config = AppConfig()
        client_name = app_config.get(TA_OAUTH_CLIENT_NAME.env_name)

        # Build token request
        token_request = TokenRequest(
            token_endpoint=token_endpoint,
            grant_type="authorization_code",
            code=code,
            redirect_uri=server_config.oauth_redirect_uri,
            code_verifier=flow_state.verifier,
            resource=flow_state.resource,
            client_id=server_config.oauth_client_id or client_name,
            client_secret=server_config.oauth_client_secret,
        )

        # Exchange code for tokens
        token_response = await self.exchange_code_for_tokens(token_request)

        # Create OAuth2AuthData
        oauth_data = OAuth2AuthData(
            access_token=token_response.access_token,
            refresh_token=token_response.refresh_token,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=token_response.expires_in),
            scopes=token_response.scope.split() if token_response.scope else flow_state.scopes,
            audience=token_response.aud,
            resource=flow_state.resource,
            token_type=token_response.token_type,
            issued_at=datetime.now(timezone.utc),
        )

        # Store in AuthStorage
        composite_key = build_auth_storage_key(server_config.auth_server, oauth_data.scopes)
        self.auth_storage.store(user_id, composite_key, oauth_data)

        logger.info(
            f"OAuth callback successful for {flow_state.server_name}: "
            f"user={user_id}, resource={flow_state.resource}"
        )

        # Clean up flow state
        self.state_manager.delete_flow_state(state, user_id)

        return oauth_data
