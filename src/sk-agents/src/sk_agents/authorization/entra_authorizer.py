"""
Microsoft Entra ID (Azure AD) JWT Token Authorizer.

Validates JWT tokens issued by Microsoft Entra ID and extracts user identity.
"""

import logging
from typing import Optional
import jwt
from jwt import PyJWKClient
from ska_utils import AppConfig
from sk_agents.authorization.request_authorizer import RequestAuthorizer
from sk_agents.configs import TA_ENTRA_TENANT_ID, TA_ENTRA_CLIENT_ID, TA_ENTRA_AUTHORITY

logger = logging.getLogger(__name__)


class EntraAuthorizer(RequestAuthorizer):
    """
    Authorizer that validates Microsoft Entra ID JWT tokens.
    
    Validates token signature using Entra's public keys (JWKS endpoint),
    checks expiration, and extracts user information.
    
    Environment Variables Required:
        TA_ENTRA_TENANT_ID: Your Entra tenant ID
        TA_ENTRA_CLIENT_ID: Your registered application's client ID
        TA_ENTRA_AUTHORITY: (Optional) Auth authority URL
    """
    
    def __init__(self):
        """
        Initialize Entra authorizer using environment configuration.
        
        Loads configuration from environment variables via AppConfig.
        """
        app_config = AppConfig()
        
        self.tenant_id = app_config.get(TA_ENTRA_TENANT_ID.env_name)
        self.client_id = app_config.get(TA_ENTRA_CLIENT_ID.env_name)
        authority = app_config.get(TA_ENTRA_AUTHORITY.env_name)
        
        if not self.tenant_id or not self.client_id:
            raise ValueError(
                "TA_ENTRA_TENANT_ID and TA_ENTRA_CLIENT_ID must be set "
                "to use EntraAuthorizer"
            )
        
        # Default to Microsoft public cloud if not specified
        if authority:
            self.authority = authority
        else:
            self.authority = f"https://login.microsoftonline.com/{self.tenant_id}"
        
        # JWKS endpoint for public key retrieval
        self.jwks_uri = f"{self.authority}/discovery/v2.0/keys"
        
        # Cache for JWK client (reused across requests)
        self._jwk_client: Optional[PyJWKClient] = None
        
        logger.info(f"EntraAuthorizer initialized for tenant: {self.tenant_id}")
    
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
    
    async def authorize_request(self, auth_header: str) -> str:
        """
        Validate Entra ID JWT token and extract user ID.
        
        Args:
            auth_header: Authorization header value (e.g., "Bearer eyJ0...")
            
        Returns:
            User ID (typically email or object ID from token's 'sub' or 'preferred_username')
            
        Raises:
            ValueError: If token is invalid, expired, or missing
        """
        if not auth_header:
            raise ValueError("Authorization header is required")
        
        # Extract token from "Bearer <token>" format
        if not auth_header.startswith("Bearer "):
            raise ValueError("Authorization header must use Bearer scheme")
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        
        try:
            # Get signing key from JWKS endpoint
            jwk_client = self._get_jwk_client()
            signing_key = jwk_client.get_signing_key_from_jwt(token)
            
            # Decode and validate token
            decoded_token = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=self.client_id,  # Validate token is for our app
                issuer=f"{self.authority}/v2.0",  # Validate issuer
                options={
                    "verify_signature": True,
                    "verify_exp": True,
                    "verify_aud": True,
                    "verify_iss": True,
                }
            )
            
            # Extract user ID - try multiple claims in order of preference
            user_id = (
                decoded_token.get("preferred_username") or  # Usually email
                decoded_token.get("upn") or  # User Principal Name
                decoded_token.get("email") or  # Email claim
                decoded_token.get("sub") or  # Subject (object ID)
                decoded_token.get("oid")  # Object ID
            )
            
            if not user_id:
                raise ValueError("Token does not contain user identifier")
            
            # Log additional useful info for debugging
            logger.debug(f"Token validated for user: {user_id}")
            logger.debug(f"Token groups: {decoded_token.get('groups', [])}")
            logger.debug(f"Token roles: {decoded_token.get('roles', [])}")
            
            return user_id
            
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
    
    def extract_user_groups(self, auth_header: str) -> list[str]:
        """
        Extract user's Entra groups from JWT token.
        
        Useful for future entitlement filtering based on group membership.
        
        Args:
            auth_header: Authorization header value
            
        Returns:
            List of group IDs/names
        """
        if not auth_header or not auth_header.startswith("Bearer "):
            return []
        
        token = auth_header[7:]
        
        try:
            # Decode without validation (just to read claims)
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded.get("groups", [])
        except Exception as e:
            logger.warning(f"Failed to extract groups from token: {e}")
            return []
    
    def extract_user_roles(self, auth_header: str) -> list[str]:
        """
        Extract user's Entra roles from JWT token.
        
        Args:
            auth_header: Authorization header value
            
        Returns:
            List of role names
        """
        if not auth_header or not auth_header.startswith("Bearer "):
            return []
        
        token = auth_header[7:]
        
        try:
            # Decode without validation (just to read claims)
            decoded = jwt.decode(token, options={"verify_signature": False})
            return decoded.get("roles", [])
        except Exception as e:
            logger.warning(f"Failed to extract roles from token: {e}")
            return []

