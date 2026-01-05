"""
Authorization Server Metadata Discovery

Implements server metadata discovery per RFC8414 and RFC9728.
Used for dynamic discovery of OAuth endpoints and capabilities.

References:
- RFC 8414: OAuth 2.0 Authorization Server Metadata
- RFC 9728: OAuth 2.0 Protected Resource Metadata
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta
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
    revocation_endpoint: HttpUrl | None = None
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

    Implements RFC 8414 and RFC 9728 discovery with TTL-based caching.
    """

    def __init__(self, timeout: float = 30.0, ttl: int = 3600):
        """
        Initialize metadata cache.

        Args:
            timeout: HTTP request timeout in seconds (default: 30)
            ttl: Cache TTL in seconds (default: 3600 = 1 hour)
        """
        self.timeout = timeout
        self.ttl = ttl
        self._cache: dict[str, tuple[Any, datetime]] = {}
        self._lock = asyncio.Lock()

    async def fetch_auth_server_metadata(self, auth_server: str) -> AuthServerMetadata:
        """
        Fetch authorization server metadata from well-known endpoint.

        Per RFC 8414, discovers OAuth endpoints from:
        {auth_server}/.well-known/oauth-authorization-server

        Args:
            auth_server: Authorization server base URL

        Returns:
            AuthServerMetadata: Parsed metadata

        Raises:
            httpx.HTTPError: If discovery fails
            ValueError: If metadata is invalid
        """
        # Check cache first
        async with self._lock:
            if auth_server in self._cache:
                metadata, cached_at = self._cache[auth_server]
                if datetime.now(UTC) - cached_at < timedelta(seconds=self.ttl):
                    logger.debug(f"Cache hit for auth server metadata: {auth_server}")
                    return metadata

        # Fetch from well-known endpoint
        well_known_url = f"{auth_server.rstrip('/')}/.well-known/oauth-authorization-server"
        logger.info(f"Discovering authorization server metadata from {well_known_url}")

        data = None  # Initialize to avoid scope issues
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(well_known_url)
                response.raise_for_status()
                data = response.json()

            # Parse and validate
            metadata = AuthServerMetadata(**data)

            # Validate PKCE support (MCP requirement)
            if metadata.code_challenge_methods_supported:
                if "S256" not in metadata.code_challenge_methods_supported:
                    logger.warning(
                        f"Auth server {auth_server} does not advertise S256 PKCE support. "
                        f"Supported methods: {metadata.code_challenge_methods_supported}"
                    )
            else:
                logger.warning(
                    f"Auth server {auth_server} does not advertise code_challenge_methods_supported"
                )

            logger.info(
                f"Successfully discovered metadata for {auth_server}: "
                f"authorization_endpoint={metadata.authorization_endpoint}, "
                f"token_endpoint={metadata.token_endpoint}"
            )

            # Cache result
            async with self._lock:
                self._cache[auth_server] = (metadata, datetime.now(UTC))

            return metadata

        except httpx.HTTPStatusError as e:
            logger.error(
                f"Failed to fetch authorization server metadata from {well_known_url}: "
                f"HTTP {e.response.status_code}"
            )
            raise
        except httpx.HTTPError as e:
            logger.error(f"Network error fetching authorization server metadata: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse authorization server metadata: {e}")
            raise ValueError(f"Invalid authorization server metadata: {e}") from e

    async def fetch_protected_resource_metadata(
        self, mcp_server: str
    ) -> ProtectedResourceMetadata | None:
        """
        Fetch protected resource metadata from MCP server.

        Per RFC 9728, discovers resource metadata from:
        {mcp_server}/.well-known/oauth-protected-resource

        Note: This metadata is OPTIONAL per RFC 9728. Returns None if not available.

        Args:
            mcp_server: MCP server base URL

        Returns:
            ProtectedResourceMetadata: Parsed metadata, or None if not available

        Raises:
            ValueError: If metadata exists but is invalid
        """
        # Check cache first
        cache_key = f"prm:{mcp_server}"
        async with self._lock:
            if cache_key in self._cache:
                metadata, cached_at = self._cache[cache_key]
                if datetime.now(UTC) - cached_at < timedelta(seconds=self.ttl):
                    logger.debug(f"Cache hit for protected resource metadata: {mcp_server}")
                    return metadata

        # Fetch from well-known endpoint
        well_known_url = f"{mcp_server.rstrip('/')}/.well-known/oauth-protected-resource"
        logger.info(f"Discovering protected resource metadata from {well_known_url}")

        data = None  # Initialize to avoid scope issues
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(well_known_url)

                # 404 is acceptable - PRM is optional
                if response.status_code == 404:
                    logger.debug(
                        f"Protected resource metadata not available for {mcp_server} (404). "
                        f"This is optional per RFC 9728."
                    )
                    # Cache the None result to avoid repeated requests
                    async with self._lock:
                        self._cache[cache_key] = (None, datetime.now(UTC))
                    return None

                response.raise_for_status()
                data = response.json()

            # Parse and validate
            metadata = ProtectedResourceMetadata(**data)

            # Validate authorization_servers is non-empty
            if not metadata.authorization_servers:
                raise ValueError("Protected resource metadata must include authorization_servers")

            logger.info(
                f"Successfully discovered protected resource metadata for {mcp_server}: "
                f"authorization_servers={metadata.authorization_servers}, "
                f"scopes_supported={metadata.scopes_supported}"
            )

            # Cache result
            async with self._lock:
                self._cache[cache_key] = (metadata, datetime.now(UTC))

            return metadata

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                # Already handled above, but just in case
                async with self._lock:
                    self._cache[cache_key] = (None, datetime.now(UTC))
                return None
            logger.error(
                f"Failed to fetch protected resource metadata from {well_known_url}: "
                f"HTTP {e.response.status_code}"
            )
            raise
        except httpx.HTTPError as e:
            logger.error(f"Network error fetching protected resource metadata: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to parse protected resource metadata: {e}")
            raise ValueError(f"Invalid protected resource metadata: {e}") from e
