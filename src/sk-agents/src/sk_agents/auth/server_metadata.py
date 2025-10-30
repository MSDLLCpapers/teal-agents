"""
Authorization Server Metadata Discovery

Implements server metadata discovery per RFC8414 and RFC9728.
Used for dynamic discovery of OAuth endpoints and capabilities.

References:
- RFC 8414: OAuth 2.0 Authorization Server Metadata
- RFC 9728: OAuth 2.0 Protected Resource Metadata
"""

import logging
from typing import Any

import httpx
from pydantic import BaseModel, HttpUrl

logger = logging.getLogger(__name__)


class AuthServerMetadata(BaseModel):
    """
    OAuth 2.0 Authorization Server Metadata (RFC8414)

    Discovered from {auth_server}/.well-known/oauth-authorization-server
    """

    issuer: HttpUrl
    authorization_endpoint: HttpUrl
    token_endpoint: HttpUrl
    registration_endpoint: HttpUrl | None = None
    response_types_supported: list[str]
    grant_types_supported: list[str] | None = None
    code_challenge_methods_supported: list[str] | None = None
    scopes_supported: list[str] | None = None


class ProtectedResourceMetadata(BaseModel):
    """
    OAuth 2.0 Protected Resource Metadata (RFC9728)

    Discovered from {mcp_server}/.well-known/oauth-protected-resource
    """

    resource: HttpUrl
    authorization_servers: list[HttpUrl]
    scopes_supported: list[str] | None = None
    bearer_methods_supported: list[str] | None = None


class ServerMetadataCache:
    """
    Cache for server metadata to avoid repeated discovery requests.

    Phase 3 implementation (optional).
    """

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._cache: dict[str, Any] = {}

    async def fetch_auth_server_metadata(self, auth_server: str) -> AuthServerMetadata:
        """
        Fetch authorization server metadata from well-known endpoint.

        Args:
            auth_server: Authorization server base URL

        Returns:
            AuthServerMetadata: Parsed metadata

        Raises:
            httpx.HTTPError: If discovery fails
        """
        # Implementation in Phase 3
        raise NotImplementedError("Server metadata discovery not yet implemented (Phase 3)")

    async def fetch_protected_resource_metadata(self, mcp_server: str) -> ProtectedResourceMetadata:
        """
        Fetch protected resource metadata from MCP server.

        Args:
            mcp_server: MCP server base URL

        Returns:
            ProtectedResourceMetadata: Parsed metadata

        Raises:
            httpx.HTTPError: If discovery fails
        """
        # Implementation in Phase 3
        raise NotImplementedError("Protected resource metadata discovery not yet implemented (Phase 3)")
