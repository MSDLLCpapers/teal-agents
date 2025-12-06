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
from sk_agents.auth.server_metadata import ServerMetadataCache
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
        self.metadata_cache = ServerMetadataCache(timeout=timeout)
        self.auth_storage_factory = AuthStorageFactory(AppConfig())
        self.auth_storage = self.auth_storage_factory.get_auth_storage_manager()

    @staticmethod
    def should_include_resource_param(protocol_version: str | None = None, has_prm: bool = False) -> bool:
        """
        Determine if resource parameter should be included in OAuth requests.

        Per MCP specification 2025-06-18:
        - resource parameter MUST be included if protocol version >= 2025-06-18
        - resource parameter MUST be included if Protected Resource Metadata discovered
        - Otherwise, resource parameter SHOULD be omitted for backward compatibility

        Args:
            protocol_version: MCP protocol version (e.g., "2025-06-18")
            has_prm: Whether Protected Resource Metadata has been discovered

        Returns:
            bool: True if resource parameter should be included
        """
        # If we have Protected Resource Metadata, always include resource param
        if has_prm:
            return True

        # If no protocol version provided, don't include resource param (backward compat)
        if not protocol_version:
            return False

        # Check if protocol version is 2025-11-25 or later
        # Simple string comparison works for ISO date format (YYYY-MM-DD)
        try:
            return protocol_version >= "2025-11-25"
        except Exception:
            # If comparison fails, be conservative and include resource param
            logger.warning(f"Failed to compare protocol version: {protocol_version}")
            return True

    @staticmethod
    def validate_token_scopes(requested_scopes: list[str] | None, token_response: "TokenResponse") -> None:
        """
        Validate that returned scopes don't exceed requested scopes (prevents escalation attacks).

        Per OAuth 2.1 Section 3.3:
        - If scopes were requested, returned scopes MUST be a subset of requested scopes
        - Servers MUST NOT grant scopes not requested by the client
        - This prevents scope escalation attacks

        Args:
            requested_scopes: Scopes requested in authorization request
            token_response: Token response from authorization server

        Raises:
            ValueError: If scope escalation detected (returned > requested)
        """
        from sk_agents.auth.oauth_models import TokenResponse

        # If no scopes were requested, any returned scopes are acceptable
        if not requested_scopes:
            return

        # If server didn't return scope field, assume it granted all requested scopes
        # Per OAuth 2.1: "If omitted, authorization server defaults to all requested scopes"
        if not token_response.scope:
            logger.debug("Token response contains no scope field - assuming all requested scopes granted")
            return

        # Parse returned scopes (space-separated string)
        requested = set(requested_scopes)
        returned = set(token_response.scope.split())

        # Check for scope escalation: returned scopes must be subset of requested
        unauthorized_scopes = returned - requested

        if unauthorized_scopes:
            logger.error(
                f"Scope escalation attack detected! "
                f"Requested: {requested}, Returned: {returned}, Unauthorized: {unauthorized_scopes}"
            )
            raise ValueError(
                f"Server granted unauthorized scopes: {unauthorized_scopes}. "
                f"This is a scope escalation attack. Requested: {requested}, Returned: {returned}"
            )

        # Log scope reduction (informational - not an error)
        missing_scopes = requested - returned
        if missing_scopes:
            logger.warning(
                f"Server granted fewer scopes than requested. "
                f"Requested: {requested}, Granted: {returned}, Missing: {missing_scopes}"
            )
        else:
            logger.debug(f"Scope validation passed. Granted scopes: {returned}")

    def build_authorization_url(self, request: AuthorizationRequest) -> str:
        """
        Build complete OAuth authorization URL.

        Constructs URL with all required parameters:
        - response_type=code
        - client_id, redirect_uri
        - resource (canonical MCP server URI) - only if protocol version >= 2025-06-18
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
            "scope": " ".join(request.scopes),
            "state": request.state,
            "code_challenge": request.code_challenge,
            "code_challenge_method": request.code_challenge_method,
        }

        # Conditionally include resource parameter per MCP spec 2025-06-18
        if request.resource:
            params["resource"] = request.resource

        # Build URL - use discovered authorization_endpoint if available
        if request.authorization_endpoint:
            base_url = str(request.authorization_endpoint)
            logger.debug(f"Using discovered authorization endpoint: {base_url}")
        else:
            # Fallback: construct from auth_server
            base_url = str(request.auth_server).rstrip("/")
            if not base_url.endswith("/authorize"):
                base_url = f"{base_url}/authorize"
            logger.debug(f"Using fallback authorization endpoint: {base_url}")

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
        - resource (canonical URI) - only if protocol version >= 2025-06-18
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
        }

        # Conditionally include resource parameter per MCP spec 2025-06-18
        if token_request.resource:
            body["resource"] = token_request.resource

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
            
            # Validate scopes to prevent escalation attacks
            self.validate_token_scopes(token_request.requested_scopes, token_response)
            
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
            requested_scopes=refresh_request.requested_scopes,
        )

        logger.debug(f"Refreshing access token for resource={refresh_request.resource}")
        return await self.exchange_code_for_tokens(token_request)

    async def revoke_token(
        self,
        token: str,
        revocation_endpoint: str,
        client_id: str,
        client_secret: str | None = None,
        token_type_hint: str = "access_token"
    ) -> None:
        """
        Revoke an access or refresh token per RFC 7009.

        This allows clients to notify the authorization server that a token
        is no longer needed, enabling immediate invalidation.

        Args:
            token: The token to revoke (access or refresh token)
            revocation_endpoint: Token revocation endpoint URL
            client_id: OAuth client ID
            client_secret: OAuth client secret (for confidential clients)
            token_type_hint: Hint about token type ("access_token" or "refresh_token")

        Raises:
            httpx.HTTPError: If revocation request fails
        """
        # Build request body per RFC 7009
        body = {
            "token": token,
            "token_type_hint": token_type_hint,
            "client_id": client_id,
        }

        # Add client secret if provided (confidential clients)
        if client_secret:
            body["client_secret"] = client_secret

        logger.debug(f"Revoking token: endpoint={revocation_endpoint}, type_hint={token_type_hint}")

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    revocation_endpoint,
                    data=body,
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                )

                # Per RFC 7009: Server responds with 200 regardless of token validity
                # This prevents token scanning attacks
                if response.status_code == 200:
                    logger.info(f"Successfully revoked token (type_hint={token_type_hint})")
                else:
                    logger.warning(
                        f"Token revocation returned unexpected status {response.status_code}"
                    )
                    response.raise_for_status()

        except httpx.HTTPError as e:
            logger.error(f"Failed to revoke token: {e}")
            raise

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

        # Discover Protected Resource Metadata (RFC 9728) if HTTP MCP server
        has_prm = False
        if server_config.url:  # Only for HTTP MCP servers
            try:
                prm = await self.metadata_cache.fetch_protected_resource_metadata(server_config.url)
                has_prm = prm is not None
                if prm:
                    logger.info(f"Discovered PRM for {server_config.name}: auth_servers={prm.authorization_servers}")
            except Exception as e:
                logger.debug(f"PRM discovery failed (optional): {e}")
                has_prm = False

        # Determine if resource parameter should be included (per MCP spec 2025-06-18)
        include_resource = self.should_include_resource_param(
            protocol_version=server_config.protocol_version,
            has_prm=has_prm
        )

        # Get canonical resource URI if needed
        resource = None
        if include_resource:
            try:
                resource = server_config.effective_canonical_uri
            except ValueError as e:
                logger.warning(f"Cannot determine canonical URI for {server_config.name}: {e}. Proceeding without resource parameter.")
                resource = None

        # Generate PKCE pair
        verifier, challenge = self.pkce_manager.generate_pkce_pair()

        # Generate state
        state = self.state_manager.generate_state()

        # Store flow state (always store resource for validation, even if not sent in auth request)
        self.state_manager.store_flow_state(
            state=state,
            verifier=verifier,
            user_id=user_id,
            server_name=server_config.name,
            resource=resource or server_config.url or "",  # Store for future reference
            scopes=server_config.scopes,
        )

        # Get client configuration
        app_config = AppConfig()
        client_name = app_config.get(TA_OAUTH_CLIENT_NAME.env_name)

        # Discover authorization server metadata (RFC 8414)
        authorization_endpoint = None
        metadata = None
        try:
            metadata = await self.metadata_cache.fetch_auth_server_metadata(server_config.auth_server)
            authorization_endpoint = str(metadata.authorization_endpoint)
            logger.info(f"Discovered authorization endpoint: {authorization_endpoint}")
        except Exception as e:
            logger.warning(f"Failed to discover authorization server metadata: {e}. Using fallback.")
            authorization_endpoint = None

        # Try dynamic client registration if no client_id configured (RFC 7591)
        client_id = server_config.oauth_client_id or client_name
        client_secret = server_config.oauth_client_secret

        if not server_config.oauth_client_id and server_config.enable_dynamic_registration:
            try:
                # Check if metadata includes registration_endpoint
                if metadata and metadata.registration_endpoint:
                    logger.info(
                        f"No client_id configured for {server_config.name}. "
                        f"Attempting dynamic registration..."
                    )

                    from sk_agents.auth.client_registration import DynamicClientRegistration

                    registration_client = DynamicClientRegistration(timeout=self.timeout)
                    registration_response = await registration_client.register_client(
                        registration_endpoint=str(metadata.registration_endpoint),
                        redirect_uris=[str(server_config.oauth_redirect_uri)],
                        client_name=client_name,
                        scopes=server_config.scopes
                    )

                    # Use registered credentials
                    client_id = registration_response.client_id
                    client_secret = registration_response.client_secret

                    logger.info(
                        f"Successfully registered client for {server_config.name}: "
                        f"client_id={client_id}"
                    )

                    # TODO: Optionally persist client_id/secret for reuse

                else:
                    logger.warning(
                        f"Dynamic registration enabled but no registration_endpoint "
                        f"discovered for {server_config.name}"
                    )
            except Exception as e:
                logger.warning(
                    f"Dynamic client registration failed for {server_config.name}: {e}. "
                    f"Falling back to default client_id."
                )
                # Continue with default client_name

        # Build authorization request
        auth_request = AuthorizationRequest(
            auth_server=server_config.auth_server,
            authorization_endpoint=authorization_endpoint,
            client_id=client_id,
            redirect_uri=server_config.oauth_redirect_uri,
            resource=resource,  # None if protocol version < 2025-06-18
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

        # Discover Protected Resource Metadata (RFC 9728) if HTTP MCP server
        has_prm = False
        if server_config.url:  # Only for HTTP MCP servers
            try:
                prm = await self.metadata_cache.fetch_protected_resource_metadata(server_config.url)
                has_prm = prm is not None
                if prm:
                    logger.info(f"Discovered PRM for {server_config.name}: auth_servers={prm.authorization_servers}")
            except Exception as e:
                logger.debug(f"PRM discovery failed (optional): {e}")
                has_prm = False

        # Determine if resource parameter should be included (per MCP spec 2025-06-18)
        include_resource = self.should_include_resource_param(
            protocol_version=server_config.protocol_version,
            has_prm=has_prm
        )

        # Build token request
        token_request = TokenRequest(
            token_endpoint=token_endpoint,
            grant_type="authorization_code",
            code=code,
            redirect_uri=server_config.oauth_redirect_uri,
            code_verifier=flow_state.verifier,
            resource=flow_state.resource if include_resource else None,  # Conditional per protocol version
            client_id=server_config.oauth_client_id or client_name,
            client_secret=server_config.oauth_client_secret,
            requested_scopes=flow_state.scopes,  # For scope validation
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
