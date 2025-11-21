import logging
from datetime import datetime, timezone, timedelta
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from ska_utils import AppConfig

from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.auth_storage.secure_auth_storage_manager import (
    SecureAuthStorageManager,
)
from sk_agents.authorization.authorizer_factory import AuthorizerFactory
from sk_agents.authorization.request_authorizer import RequestAuthorizer
from sk_agents.configs import (
    TA_AD_GROUP_ID,
    TA_CLIENT_LOGIN_URL,
    TA_AD_CLIENT_ID,
    TA_CLIENT_SECRETS
)
logger = logging.getLogger(__name__)


class TokenRequest(BaseModel):
    """Request model for storing OAuth tokens."""
    access_token: str = Field(..., description="The OAuth access token")
    refresh_token: Optional[str] = Field(
        None, description="The OAuth refresh token"
    )
    expires_in: int = Field(
        ..., description="Token expiration time in seconds from now"
    )
    scopes: list[str] = Field(
        default_factory=list, description="Token scopes"
    )
    token_type: str = Field(default="Bearer", description="Type of the token")


class TokenRefreshRequest(BaseModel):
    """Request model for refreshing OAuth tokens using MSAL."""
    client_id: str = Field(
        ..., description="The Microsoft Entra ID application client ID"
    )
    client_secret: Optional[str] = Field(
        None, description="The client secret (for confidential clients)"
    )
    authority: str = Field(
        default=None,
        description="The  authority URL to refresh your token"
    )
    scopes: list[str] = Field(
        default_factory=list, description="Token scopes to request"
    )


class TokenResponse(BaseModel):
    """Response model for token operations."""
    message: str
    user_id: str
    expires_at: datetime


class TokenValidationResponse(BaseModel):
    """Response model for token validation."""
    valid: bool
    user_id: Optional[str] = None
    expires_at: Optional[datetime] = None
    scopes: list[str] = Field(default_factory=list)
    message: str


class AuthRoutes:
    """Authentication routes for OAuth tokens from Microsoft Entra ID."""

    MICROSOFT_ENTRA_KEY = 'place holder'

    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.auth_storage_factory = AuthStorageFactory(app_config)
        self.auth_storage_manager = (
            self.auth_storage_factory.get_auth_storage_manager()
        )
        self.authorizer_factory = AuthorizerFactory(app_config)
        self.authorizer = self.authorizer_factory.get_authorizer()
        self.httpx_client = httpx.AsyncClient(timeout=20.0)
        self.client_identity_url = app_config.get(TA_CLIENT_LOGIN_URL.env_name)
        self.tenant_id = app_config.get(TA_AD_GROUP_ID.env_name)
        self.code_auth_endpoint = f"{self.client_identity_url}/{self.tenant_id}/oauth2/v2.0/token"
        self.client_id = app_config.get(TA_AD_CLIENT_ID.env_name)
        self.client_secret = app_config.get(TA_CLIENT_SECRETS.env_name)

    def get_auth_storage_manager(self) -> SecureAuthStorageManager:
        """Get the configured auth storage manager."""
        return self.auth_storage_manager

    def get_authorizer(self) -> RequestAuthorizer:
        """Get the configured request authorizer."""
        return self.authorizer

    async def get_user_id_from_auth(self, authorization: str) -> str:
        """Extract user ID from authorization header."""
        try:
            user_id = await self.authorizer.authorize_request(authorization)
            return user_id
        except ValueError as e:
            logger.warning(f"Authorization failed: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required"
            ) from e
        except Exception as e:
            logger.error(f"Unexpected error during authorization: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal authentication error"
            ) from e

    def get_routes(self) -> APIRouter:
        """Create and return the authentication routes."""
        router = APIRouter(prefix="/auth", tags=["Authentication"])

        @router.post(
            "/token/store/redirectUri/",
            response_model=TokenResponse,
            summary="Store OAuth token",
            description="Store OAuth token from Microsoft Entra ID login",
        )
        async def store_redirect_token(
            request: Request
        ) -> TokenResponse:
            """
            Store an OAuth token for the authenticated user.

            This endpoint accepts an OAuth token (typically received after
            Microsoft Entra ID login) and stores it securely for future use.
            """
            body_json = await request.form()
            logger.info(f"Query params: {dict(request.query_params.items())}")
            logger.info(f"Path params: {dict(request.path_params.items())}")
            logger.info(f"Headers: {dict(request.headers.items())}")
            logger.info(f"Body: {body_json}")
            authorization = body_json.get("code")
            if not authorization:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Code Parameter missing required"
                )

            try:
                # Get user ID from the authorization header
                url = self.code_auth_endpoint
                payload = {
                    "code": authorization,
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret
                }
                response = await self.httpx_client.post(url, data=payload)
                response_data = response.json()
                logger.info(f"token response: {response_data}")
                expires_at = datetime.now(timezone.utc).replace(microsecond=0)
                expires_in = response_data.get("expires_in", 3600)
                expires_at = expires_at + timedelta(seconds=expires_in)
                scopes = response_data.get("scope")
                scope_list = scopes.split()
                access_token = response_data.get("access_token")
                # Create OAuth2 auth data
                auth_data = OAuth2AuthData(
                    access_token=access_token,
                    refresh_token=response_data.get("refresh_token"),
                    expires_at=expires_at,
                    scopes=scope_list
                )
                user_id = await self.get_user_id_from_auth(access_token)
                # Store the token
                self.auth_storage_manager.store(
                    user_id, self.client_id, auth_data
                )

                logger.info(
                    f"Successfully stored OAuth token for user: {response_data}"
                )

                return TokenResponse(
                    message="Token stored successfully",
                    user_id=response_data['access_token'],
                    expires_at=response_data['expires_in']
                )

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error storing token: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to store token"
                ) from e

        @router.delete(
            "/token/revoke",
            summary="Revoke stored token",
            description="Delete stored OAuth token for authenticated user",
        )
        async def revoke_token(request: Request) -> dict:
            """
            Revoke (delete) the stored OAuth token for the authenticated user.

            This endpoint removes the stored token from the auth storage,
            effectively revoking the user's stored authentication.
            """
            authorization = request.headers.get("authorization")
            if not authorization:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authorization header required"
                )

            try:
                # Get user ID from the authorization header
                user_id = await self.get_user_id_from_auth(authorization)

                # Check if token exists before deletion
                auth_data = self.auth_storage_manager.retrieve(
                    user_id, self.client_id
                )

                if not auth_data:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail="No stored token found for user"
                    )

                # Delete the token
                self.auth_storage_manager.delete(
                    user_id, self.client_id
                )

                logger.info(f"Successfully revoked token for user: {user_id}")

                return {
                    "message": "Token revoked successfully",
                    "user_id": user_id
                }

            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error revoking token: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Failed to revoke token"
                ) from e

        return router
