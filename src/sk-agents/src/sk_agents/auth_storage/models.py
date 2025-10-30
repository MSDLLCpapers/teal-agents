from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class BaseAuthData(BaseModel):
    auth_type: str


class OAuth2AuthData(BaseAuthData):
    auth_type: Literal["oauth2"] = "oauth2"
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime
    # The scopes this token is valid for.
    scopes: list[str] = []

    # MCP OAuth 2.1 Compliance Fields
    audience: str | None = None  # Token audience (aud) for validation
    resource: str | None = None  # Resource binding (canonical MCP server URI)
    token_type: str = "Bearer"  # Token type (usually "Bearer")
    issued_at: datetime | None = None  # Token issue timestamp

    def is_valid_for_resource(self, resource_uri: str) -> bool:
        """
        Validate token is valid for specific resource.

        Checks:
        1. Token not expired
        2. Resource matches (if resource binding present)
        3. Audience matches (if audience present)

        Args:
            resource_uri: Canonical MCP server URI to validate against

        Returns:
            bool: True if token is valid for this resource
        """
        from datetime import datetime, timezone

        # Check expiry
        if self.expires_at <= datetime.now(timezone.utc):
            return False

        # Check resource binding (MCP-specific)
        if self.resource and self.resource != resource_uri:
            return False

        # Check audience (OAuth 2.1 token audience validation)
        if self.audience and self.audience != resource_uri:
            return False

        return True


# A union of all supported auth data types.
# Right now only OAuth2 is supported, but when more are added
# the below will need to be updated to a discriminated union.
#
# For example:
# AuthData = Union[OAuth2AuthData, AnotherAuthData]
AuthData = OAuth2AuthData
