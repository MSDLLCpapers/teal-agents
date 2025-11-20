import logging
from typing import Optional
import jwt
from jwt import PyJWKClient
from ska_utils import AppConfig
from fastapi import HTTPException, status
from sk_agents.authorization.request_authorizer import RequestAuthorizer
from datetime import datetime, timezone, timedelta
from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.configs import (
    TA_AD_GROUP_ID,
    TA_AD_CLIENT_ID,
    TA_CLIENT_SECRETS,
    TA_AD_AUTHORITY,
    TA_PLATFORM_CLIENT_ID,
    TA_PLATFORM_AUTHORITY,
    TA_SCOPES
)
import httpx
logger = logging.getLogger(__name__)


class AzureEntraAuthorizer(RequestAuthorizer):
    """
    This Authorizer handles validating tokens issued by the platform's
    Microsoft Azure Entra App registration

    This authorizer will handle:
        - token validation
    """

    def __init__(self):
        app_config = AppConfig()

        # Get configuration values
        self.tenant_id = app_config.get(TA_AD_GROUP_ID.env_name)
        self.client_id = app_config.get(TA_AD_CLIENT_ID.env_name)
        self.client_secret = app_config.get(TA_CLIENT_SECRETS.env_name)
        self.authority = app_config.get(TA_AD_AUTHORITY.env_name)
        self.plt_client_id = app_config.get(TA_PLATFORM_CLIENT_ID.env_name)
        self.plt_authority = app_config.get(TA_PLATFORM_AUTHORITY.env_name)
        self.default_entra_url = "https://login.microsoftonline.com/"
        self.entra_jwks_endpoint = "/discovery/v2.0/keys"
        self.entra_token_endpoint = "common/oauth2/v2.0/token"
        self.entra_refresh_token_grant_type = "refresh_token"
        self.scopes = app_config.get(TA_SCOPES.env_name)
        self._jwk_client: Optional[PyJWKClient] = None
        self.jwks_uri = None
        if not self.tenant_id or not self.client_id:
            raise ValueError(
                f"Required configuration missing: "
                f"TA_AD_GROUP_ID={'set' if self.tenant_id else 'missing'}, "
                f"TA_AD_CLIENT_ID={'set' if self.client_id else 'missing'}"
            )

        if self.authority is None:
            self.authority = f"{self.default_entra_url}{self.tenant_id}"

        self.jwks_uri = f"{self.authority}{self.entra_jwks_endpoint}"
        self._jwk_client = self._get_jwk_client()
        self.auth_base_url = (
            f"{self.default_entra_url}{self.tenant_id}/oauth2/v2.0/authorize?client_id={self.client_id}"
        )
        self.auth_extension_url = f"&response_type=code&response_mode=form_post&scope=offline_access {self.scopes}"
        self.auth_full_url = f"{self.auth_base_url}{self.auth_extension_url}"
        self.httpx_client = httpx.AsyncClient(timeout=20.0)

    def _get_jwk_client(self) -> PyJWKClient:
        """Get or create JWK client for public key retrieval."""
        if self._jwk_client is None:
            self._jwk_client = PyJWKClient(
                self.jwks_uri,
                cache_keys=True,
                max_cached_keys=16,
                cache_jwk_set=True,
                lifespan=3600  # Cache for 1 hour
            )
        return self._jwk_client

    def _decode_and_validate_token(self, token: str) -> dict:
        """
        Decode and validate a JWT token.

        Args:
            token: JWT token string

        Returns:
            Decoded token payload as dictionary

        Raises:
            ValueError: If token is invalid, expired, or verification fails
        """
        try:
            # Decode token without validation
            decoded_token = jwt.decode(
                token,
                options={"verify_signature": False},
                algorithms=["RS256"]
            )

            return decoded_token

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise ValueError("Token has expired")
        except jwt.InvalidAudienceError:
            logger.warning(f"JWT audience mismatch. Expected: {self.client_id}")
            raise ValueError("Token audience mismatch")
        except jwt.InvalidIssuerError:
            logger.warning(f"JWT issuer mismatch. Expected: {self.authority}/v2.0")
            raise ValueError("Token issuer mismatch")
        except jwt.InvalidSignatureError:
            logger.warning("JWT signature validation failed")
            raise ValueError("Invalid token signature")
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            raise ValueError(f"Token validation failed: {str(e)}")

    def _decode_validated_platform_token(self, token: str) -> dict:
        try:
            # Get the signing key from the JWK client
            signing_key = self._jwk_client.get_signing_key_from_jwt(token)

            # Decode and validate token with signature verification
            decoded_token = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.plt_client_id,
                issuer=f"{self.plt_authority}/v2.0"
            )

            return decoded_token

        except jwt.ExpiredSignatureError:
            logger.warning("JWT token has expired")
            raise ValueError("Token has expired")
        except jwt.InvalidAudienceError:
            logger.warning(f"JWT audience mismatch. Expected: {self.client_id}")
            raise ValueError("Token audience mismatch")
        except jwt.InvalidIssuerError:
            logger.warning(f"JWT issuer mismatch. Expected: {self.authority}/v2.0")
            raise ValueError("Token issuer mismatch")
        except jwt.InvalidSignatureError:
            logger.warning("JWT signature validation failed")
            raise ValueError("Invalid token signature")
        except Exception as e:
            logger.error(f"Token validation failed: {e}")
            raise ValueError(f"Token validation failed: {str(e)}")

    async def authorize_request(self, auth_header: str) -> str:
        """
        Validate Entra ID JWT token and extract user ID.

        Args:
            auth_header: Authorization header value (e.g., "Bearer eyJ0...")

        Returns:
           Entra Object ID for a user()

        Raises:
            ValueError: If token is invalid, expired, or missing
        """
        if not auth_header:
            return None

        token = auth_header

        try:
            decoded_token = self._decode_and_validate_token(token)

            user_id = decoded_token.get("oid")  # Object ID

            if not user_id:
                return None

            return user_id

        except Exception as error:
            logger.exception(error)
            return None

    async def validate_platform_auth(self, auth_token):
        if not auth_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Platform token"
            )

        token = auth_token

        try:
            decoded_token = self._decode_validated_platform_token(token)

            user_id = decoded_token.get("oid")  # Object ID

            if not user_id:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid Platform token"
                )

            return token

        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Platform token"
            )

    async def refresh_access_token(self, refresh_token: str):
        try:
            url = f"{self.default_entra_url}{self.entra_token_endpoint}"
            payload = {
                "refresh_token": refresh_token,
                "grant_type": self.entra_refresh_token_grant_type,
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
            return auth_data
        except Exception as error:
            logger.info(error)
            return None

    async def get_auth_url(self) -> str:
        return self.auth_full_url