"""
Dynamic Client Registration

Implements dynamic client registration per RFC7591.
Allows automatic OAuth client registration with authorization servers.

References:
- RFC 7591: OAuth 2.0 Dynamic Client Registration Protocol
"""

import logging
from typing import Literal

import httpx
from pydantic import BaseModel, HttpUrl

logger = logging.getLogger(__name__)


class ClientRegistrationRequest(BaseModel):
    """
    OAuth 2.0 Dynamic Client Registration Request (RFC7591)
    """

    client_name: str = "teal-agents"
    redirect_uris: list[HttpUrl]
    grant_types: list[Literal["authorization_code", "refresh_token"]] = [
        "authorization_code",
        "refresh_token",
    ]
    token_endpoint_auth_method: Literal["none", "client_secret_basic", "client_secret_post"] = "none"
    response_types: list[str] = ["code"]
    scope: str | None = None


class ClientRegistrationResponse(BaseModel):
    """
    OAuth 2.0 Dynamic Client Registration Response (RFC7591)
    """

    client_id: str
    client_secret: str | None = None
    client_id_issued_at: int | None = None
    client_secret_expires_at: int | None = None
    registration_access_token: str | None = None
    registration_client_uri: HttpUrl | None = None


class DynamicClientRegistration:
    """
    Dynamic Client Registration Client.

    Handles automatic OAuth client registration.
    Phase 3 implementation (optional).
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    async def register_client(
        self,
        registration_endpoint: str,
        request: ClientRegistrationRequest,
    ) -> ClientRegistrationResponse:
        """
        Register OAuth client with authorization server.

        Args:
            registration_endpoint: Registration endpoint URL from server metadata
            request: Client registration request

        Returns:
            ClientRegistrationResponse: Registered client credentials

        Raises:
            httpx.HTTPError: If registration fails
        """
        # Implementation in Phase 3
        raise NotImplementedError("Dynamic client registration not yet implemented (Phase 3)")

    async def update_client(
        self,
        registration_client_uri: str,
        registration_access_token: str,
        request: ClientRegistrationRequest,
    ) -> ClientRegistrationResponse:
        """
        Update registered OAuth client configuration.

        Args:
            registration_client_uri: Client configuration URI
            registration_access_token: Access token for client management
            request: Updated client configuration

        Returns:
            ClientRegistrationResponse: Updated client credentials
        """
        # Implementation in Phase 3
        raise NotImplementedError("Dynamic client update not yet implemented (Phase 3)")
