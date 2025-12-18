"""
MCP Client for Teal Agents Platform - Clean Implementation

This module provides an MCP (Model Context Protocol) client that supports only
the transports that are actually available in the MCP Python SDK.

ONLY SUPPORTED TRANSPORTS:
- stdio: Local subprocess communication
- http: HTTP with Server-Sent Events for remote servers

WebSocket support will be added when it becomes available in the MCP SDK.
"""

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from contextlib import AsyncExitStack
from datetime import UTC
from typing import Any

import httpx
from mcp import ClientSession, StdioServerParameters
from semantic_kernel.functions import kernel_function
from ska_utils import AppConfig

from sk_agents.auth.oauth_error_handler import OAuthErrorHandler
from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.plugin_catalog.models import (
    Governance,
    GovernanceOverride,
)
from sk_agents.ska_types import BasePlugin
from sk_agents.tealagents.v1alpha1.config import McpServerConfig

logger = logging.getLogger(__name__)


class AuthRequiredError(Exception):
    """
    Exception raised when MCP server authentication is required but missing.

    This exception is raised during discovery when a server requires authentication
    (has auth_server + scopes configured) but the user has no valid token in AuthStorage.
    """

    def __init__(self, server_name: str, auth_server: str, scopes: list[str], message: str = None):
        self.server_name = server_name
        self.auth_server = auth_server
        self.scopes = scopes
        self.message = message or f"Authentication required for MCP server '{server_name}'"
        super().__init__(self.message)


def build_auth_storage_key(auth_server: str, scopes: list[str]) -> str:
    """Create deterministic key for storing OAuth tokens in AuthStorage."""
    normalized_scopes = "|".join(sorted(scopes)) if scopes else ""
    return f"{auth_server}|{normalized_scopes}" if normalized_scopes else auth_server


def normalize_canonical_uri(uri: str) -> str:
    """
    Normalize URI to canonical format for MCP resource parameter.

    Per MCP specification, canonical URI must be:
    - Absolute URI with scheme
    - Lowercase scheme and host
    - Optional port (only if non-standard)
    - Optional path

    Examples:
        "HTTPS://API.Example.COM/mcp" -> "https://api.example.com/mcp"
        "https://example.com:443/mcp" -> "https://example.com/mcp"
        "https://example.com:8443/mcp" -> "https://example.com:8443/mcp"

    Args:
        uri: URI to normalize

    Returns:
        str: Normalized canonical URI

    Raises:
        ValueError: If URI is invalid or not absolute
    """
    from urllib.parse import urlparse, urlunparse

    if not uri:
        raise ValueError("URI cannot be empty")

    # Parse URI
    try:
        parsed = urlparse(uri)
    except Exception as e:
        raise ValueError(f"Invalid URI format: {e}") from e

    # Require absolute URI with scheme
    if not parsed.scheme:
        raise ValueError(f"URI must be absolute with scheme (got: {uri})")

    # Require host
    if not parsed.netloc:
        raise ValueError(f"URI must have a host component (got: {uri})")

    # Normalize scheme and host to lowercase
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Remove default ports (80 for http, 443 for https)
    if ":" in netloc:
        host, port = netloc.rsplit(":", 1)
        try:
            port_num = int(port)
            # Remove default ports
            if (scheme == "http" and port_num == 80) or (scheme == "https" and port_num == 443):
                netloc = host
        except ValueError:
            # Not a valid port number, keep as is
            pass

    # Reconstruct canonical URI
    canonical = urlunparse(
        (
            scheme,
            netloc,
            parsed.path or "",  # Include path if present
            "",  # No params
            "",  # No query
            "",  # No fragment
        )
    )

    logger.debug(f"Normalized canonical URI: {uri} -> {canonical}")
    return canonical


def validate_https_url(url: str, allow_localhost: bool = True) -> bool:
    """
    Validate that URL uses HTTPS (or localhost for development).

    Per MCP spec and OAuth 2.1, all endpoints must use HTTPS except localhost.

    Args:
        url: URL to validate
        allow_localhost: Allow http://localhost or http://127.0.0.1

    Returns:
        bool: True if valid, False otherwise
    """
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url)
        scheme = parsed.scheme.lower()
        hostname = parsed.hostname

        # HTTPS is always valid
        if scheme == "https":
            return True

        # HTTP is only valid for localhost/127.0.0.1/::1 if allowed
        if scheme == "http" and allow_localhost:
            if hostname in ("localhost", "127.0.0.1", "::1"):
                return True

        return False
    except Exception:
        return False


def get_package_version() -> str:
    """Get package version for MCP client identification."""
    try:
        from importlib.metadata import version

        return version("sk-agents")
    except Exception:
        return "1.0.0"  # Fallback version


def validate_mcp_sdk_version() -> None:
    """
    Validate MCP SDK version compatibility.

    Logs warnings if the installed MCP SDK version is too old to support all features.
    """
    try:
        import mcp

        version_str = getattr(mcp, "__version__", "0.0.0")

        # Parse version components
        try:
            from packaging import version as pkg_version

            installed_version = pkg_version.parse(version_str)
            required_version = pkg_version.parse("1.23.0")

            if installed_version < required_version:
                logger.warning(
                    f"MCP SDK version {version_str} detected. "
                    f"Required: >= 1.23.0 for MCP spec 2025-11-25. "
                    f"Please upgrade the MCP SDK."
                )
            else:
                logger.debug(f"MCP SDK version {version_str} is compatible")
        except ImportError:
            # packaging not available, do basic string comparison
            logger.debug(f"MCP SDK version {version_str} (could not validate compatibility)")
    except Exception as e:
        logger.warning(f"Could not validate MCP SDK version: {e}")


async def initialize_mcp_session(
    session: ClientSession,
    server_name: str,
    server_info_obj: Any = None,
    protocol_version: str = "2025-11-25",
) -> Any:
    """
    Initialize MCP session with proper protocol handshake.

    This function handles the complete MCP initialization sequence:
    1. Send initialize request with protocol version and capabilities
    2. Receive initialization result from server
    3. Send initialized notification (required by MCP spec)

    Args:
        session: The MCP ClientSession to initialize
        server_name: Name of the server for logging purposes
        server_info_obj: Optional server info object for logging

    Returns:
        The initialization result from the server

    Raises:
        ConnectionError: If initialization fails
    """
    try:
        # Step 1: Send initialize request (prefers spec path, falls back if SDK lacks args)
        try:
            init_result = await session.initialize(
                protocol_version=protocol_version,
                client_info={"name": "teal-agents", "version": get_package_version()},
                capabilities={
                    # Per MCP spec 2025-11-25: advertise root change notifications if supported
                    "roots": {"listChanged": True},
                    "sampling": {},
                    "experimental": {},
                },
            )
        except TypeError as e:
            # Older SDKs (<=1.22) don't accept keyword args; degrade gracefully.
            if "unexpected keyword argument 'protocol_version'" in str(e):
                logger.warning(
                    f"MCP SDK initialize() does not accept protocol_version/capabilities; "
                    f"falling back to legacy initialize() for '{server_name}'. "
                    f"Upgrade SDK for full 2025-11-25 compliance."
                )
                init_result = await session.initialize()
            else:
                raise

        logger.info(
            f"MCP session initialized for '{server_name}': "
            f"server={getattr(init_result, 'server_info', 'unknown')}, "
            f"protocol={getattr(init_result, 'protocol_version', 'unknown')}"
        )

        # Step 2: Send initialized notification (MCP protocol requirement)
        # Per MCP spec: "After successful initialization, the client MUST send
        # an initialized notification to indicate it is ready to begin normal operations."
        # The spec requires an initialized notification; if SDK lacks it, warn and continue.
        if hasattr(session, "send_initialized"):
            await session.send_initialized()
            logger.debug(f"Sent initialized notification to '{server_name}'")
        elif hasattr(session, "initialized"):
            await session.initialized()
            logger.debug(f"Sent initialized notification to '{server_name}'")
        else:
            logger.warning(
                f"MCP SDK missing initialized notification method for '{server_name}'. "
                f"Upgrade SDK for full spec compliance."
            )

        return init_result

    except Exception as e:
        logger.error(f"Failed to initialize MCP session for '{server_name}': {e}")
        raise ConnectionError(f"MCP session initialization failed for '{server_name}': {e}") from e


async def graceful_shutdown_session(session: ClientSession, server_name: str) -> None:
    """
    Attempt graceful MCP session shutdown.

    Per MCP spec, clients should attempt to notify servers before disconnecting.
    This is a best-effort operation and failures are logged but not raised.

    Args:
        session: The MCP ClientSession to shutdown
        server_name: Name of the server for logging purposes
    """
    try:
        if hasattr(session, "send_shutdown"):
            await session.send_shutdown()
            logger.debug(f"Sent graceful shutdown to MCP server: {server_name}")
        elif hasattr(session, "shutdown"):
            await session.shutdown()
            logger.debug(f"Sent graceful shutdown to MCP server: {server_name}")
        else:
            logger.warning(
                f"MCP SDK missing shutdown method for '{server_name}'. "
                f"Upgrade SDK for full spec compliance."
            )
    except Exception as e:
        logger.debug(f"Graceful shutdown failed for {server_name}: {e}")


def map_mcp_annotations_to_governance(
    annotations: dict[str, Any], tool_description: str = ""
) -> Governance:
    """
    Map MCP tool annotations to Teal Agents governance policies using secure-by-default approach.

    Args:
        annotations: MCP tool annotations
        tool_description: Tool description for risk analysis

    Returns:
        Governance: Governance settings for the tool
    """
    # SECURE-BY-DEFAULT: Start with HITL required for unknown tools
    requires_hitl = True
    cost = "high"
    data_sensitivity = "sensitive"

    # Only relax restrictions with explicit safe annotations
    read_only_hint = annotations.get("readOnlyHint", False)
    if read_only_hint:
        requires_hitl = False
        cost = "low"
        data_sensitivity = "public"

    # Destructive tools require HITL (already secure)
    destructive_hint = annotations.get("destructiveHint", False)
    if destructive_hint:
        requires_hitl = True
        cost = "high"
        data_sensitivity = "sensitive"

    # Enhanced risk analysis based on tool description
    if tool_description:
        description_lower = tool_description.lower()

        # Network/external access indicators
        if any(
            keyword in description_lower
            for keyword in [
                "http",
                "https",
                "api",
                "network",
                "request",
                "fetch",
                "download",
                "upload",
                "url",
                "web",
                "internet",
                "remote",
                "curl",
                "wget",
            ]
        ):
            requires_hitl = True
            cost = "high"
            data_sensitivity = "sensitive"

        # File system access indicators
        elif any(
            keyword in description_lower
            for keyword in [
                "file",
                "directory",
                "write",
                "delete",
                "create",
                "modify",
                "save",
                "remove",
                "mkdir",
                "rmdir",
                "chmod",
                "move",
                "copy",
            ]
        ):
            requires_hitl = True
            cost = "medium" if not destructive_hint else "high"
            data_sensitivity = "proprietary"

        # Code execution indicators
        elif any(
            keyword in description_lower
            for keyword in ["execute", "run", "command", "shell", "bash", "script", "eval", "exec"]
        ):
            requires_hitl = True
            cost = "high"
            data_sensitivity = "sensitive"

        # Database/storage access
        elif any(
            keyword in description_lower
            for keyword in ["database", "sql", "query", "insert", "update", "delete", "drop"]
        ):
            requires_hitl = True
            cost = "high"
            data_sensitivity = "sensitive"

    return Governance(requires_hitl=requires_hitl, cost=cost, data_sensitivity=data_sensitivity)


def apply_trust_level_governance(
    base_governance: Governance, trust_level: str, tool_description: str = ""
) -> Governance:
    """
    Apply server trust level controls to governance settings.

    Trust levels provide defense-in-depth by applying additional security controls
    based on the server's trust relationship with the platform:
    - untrusted: Maximum restrictions, force HITL for all operations
    - sandboxed: Enhanced restrictions, HITL required unless explicitly safe
    - trusted: Base governance applies, but still enforce safety on detected risks

    Args:
        base_governance: Base governance settings from MCP annotations
        trust_level: Server trust level ("trusted", "sandboxed", "untrusted")
        tool_description: Tool description for additional risk analysis

    Returns:
        Governance: Governance with trust level controls applied
    """
    if trust_level == "untrusted":
        # Force HITL for all tools from untrusted servers
        logger.debug("Applying untrusted server governance: forcing HITL")
        return Governance(requires_hitl=True, cost="high", data_sensitivity="sensitive")
    elif trust_level == "sandboxed":
        # Require HITL unless explicitly marked as safe
        # Sandboxed servers get elevated restrictions
        logger.debug("Applying sandboxed server governance: elevated restrictions")
        return Governance(
            requires_hitl=True,  # Force HITL for sandboxed servers
            cost=base_governance.cost
            if base_governance.cost != "low"
            else "medium",  # Elevate cost
            data_sensitivity=base_governance.data_sensitivity,
        )
    else:  # trusted
        # For trusted servers, use base governance but still enforce safety on high-risk operations
        # This provides defense-in-depth even for trusted sources

        # Check if tool description indicates high-risk operations
        # Even for trusted servers, certain operations should require HITL
        description_lower = tool_description.lower()
        high_risk_operations = [
            "delete",
            "remove",
            "drop",
            "truncate",
            "destroy",
            "kill",
            "execute",
            "exec",
            "eval",
            "run command",
            "shell",
            "system",
            "sudo",
            "admin",
            "root",
        ]

        has_high_risk = any(keyword in description_lower for keyword in high_risk_operations)

        if has_high_risk and not base_governance.requires_hitl:
            # Override for high-risk operations even on trusted servers
            logger.debug(
                "Trusted server tool has high-risk indicators in description, "
                "enforcing HITL despite trust level"
            )
            return Governance(
                requires_hitl=True,  # Override to require HITL
                cost="high" if base_governance.cost != "high" else base_governance.cost,
                data_sensitivity=base_governance.data_sensitivity,
            )

        # For non-high-risk operations on trusted servers, use base governance
        logger.debug("Applying trusted server governance: using base governance")
        return base_governance


def apply_governance_overrides(
    base_governance: Governance, tool_name: str, overrides: dict[str, GovernanceOverride] | None
) -> Governance:
    """
    Apply tool-specific governance overrides to base governance settings.

    Args:
        base_governance: Auto-inferred governance from MCP annotations
        tool_name: Name of the MCP tool
        overrides: Optional governance overrides from server config

    Returns:
        Governance: Final governance with overrides applied
    """
    if not overrides or tool_name not in overrides:
        return base_governance

    override = overrides[tool_name]

    # Apply selective overrides - only override specified fields
    return Governance(
        requires_hitl=override.requires_hitl
        if override.requires_hitl is not None
        else base_governance.requires_hitl,
        cost=override.cost if override.cost is not None else base_governance.cost,
        data_sensitivity=override.data_sensitivity
        if override.data_sensitivity is not None
        else base_governance.data_sensitivity,
    )


async def resolve_server_auth_headers(
    server_config: McpServerConfig,
    user_id: str = "default",
    app_config: AppConfig | None = None,
) -> dict[str, str]:
    """
    Resolve authentication headers for MCP server connection.

    Now supports automatic token refresh with OAuth 2.1 compliance:
    - Validates token audience matches resource
    - Automatically refreshes expired tokens
    - Implements token rotation per OAuth 2.1

    Args:
        server_config: MCP server configuration
        user_id: User ID for auth lookup

    Returns:
        Dict[str, str]: Headers to use for server connection

    Raises:
        AuthRequiredError: If no valid token and refresh fails
    """
    headers = {}

    # Optional per-server user header injection (opt-in via config)
    if server_config.user_id_header:
        header_name = server_config.user_id_header
        source = server_config.user_id_source
        if source == "auth" and user_id and user_id != "default":
            headers[header_name] = user_id
            logger.info(f"Set {header_name} from auth user_id for {server_config.name}")
        elif source == "env":
            env_var = server_config.user_id_env_var or header_name.upper()
            env_val = os.getenv(env_var)
            if env_val:
                headers[header_name] = env_val
                logger.info(f"Set {header_name} from env {env_var} for {server_config.name}")
            else:
                logger.warning(
                    f"user_id_source=env configured for {server_config.name} "
                    f"but env var {env_var} is not set"
                )

    # Start with any manually configured headers
    if server_config.headers:
        # If OAuth is configured, filter out Authorization headers (OAuth takes precedence)
        # If OAuth is NOT configured, keep all headers including Authorization
        for header_key, header_value in server_config.headers.items():
            if header_key.lower() == "authorization" and (
                server_config.auth_server and server_config.scopes
            ):
                logger.warning(
                    "Ignoring static Authorization header for MCP server %s (OAuth configured). "
                    "OAuth token will be used instead.",
                    server_config.name,
                )
                continue
            headers[header_key] = header_value

    # Override Arcade-User-Id with runtime user_id; fallback to env when user_id is default/absent
    fallback_arcade_user = os.getenv("ARCADE_USER_ID")
    if user_id and user_id != "default":
        headers["Arcade-User-Id"] = user_id
        logger.info(f"Overriding Arcade-User-Id header with runtime user: {user_id}")
    elif fallback_arcade_user:
        headers["Arcade-User-Id"] = fallback_arcade_user
        logger.info(f"Using fallback Arcade-User-Id from env: {fallback_arcade_user}")

    # Precompute canonical resource URI for HTTP servers (enforce presence for spec compliance)
    resource_uri: str | None = None
    if server_config.transport == "http":
        try:
            resource_uri = server_config.effective_canonical_uri
        except Exception as e:
            logger.error(f"Unable to determine canonical URI for {server_config.name}: {e}")
            raise AuthRequiredError(
                server_name=server_config.name,
                auth_server=server_config.auth_server or "unknown",
                scopes=server_config.scopes or [],
                message=f"Missing or invalid canonical URI for HTTP MCP server "
                f"'{server_config.name}'",
            ) from e

    # If server has OAuth configuration, resolve tokens using OAuth flow
    if server_config.auth_server and server_config.scopes:
        try:
            # Use AuthStorageFactory directly - no wrapper needed
            from datetime import datetime, timedelta

            from sk_agents.auth.oauth_client import OAuthClient
            from sk_agents.auth.oauth_models import RefreshTokenRequest
            from sk_agents.configs import (
                TA_MCP_OAUTH_ENABLE_AUDIENCE_VALIDATION,
                TA_MCP_OAUTH_ENABLE_TOKEN_REFRESH,
            )

            if app_config is None:
                from ska_utils import AppConfig as SkaAppConfig

                app_config = SkaAppConfig()
            auth_storage_factory = AuthStorageFactory(app_config)
            auth_storage = auth_storage_factory.get_auth_storage_manager()

            # Check feature flags
            enable_refresh = (
                app_config.get(TA_MCP_OAUTH_ENABLE_TOKEN_REFRESH.env_name).lower() == "true"
            )
            # Enforce audience/resource validation for HTTP servers regardless of flag
            if server_config.transport == "http":
                enable_audience = True
            else:
                enable_audience = (
                    app_config.get(TA_MCP_OAUTH_ENABLE_AUDIENCE_VALIDATION.env_name).lower()
                    == "true"
                )

            # Generate composite key for OAuth2 token lookup
            composite_key = build_auth_storage_key(server_config.auth_server, server_config.scopes)

            # Retrieve stored auth data
            auth_data = auth_storage.retrieve(user_id, composite_key)

            if not auth_data or not isinstance(auth_data, OAuth2AuthData):
                logger.warning(f"No valid auth token found for MCP server: {server_config.name}")
                raise AuthRequiredError(
                    server_name=server_config.name,
                    auth_server=server_config.auth_server,
                    scopes=server_config.scopes,
                )

            # Validate token for this resource (expiry + audience + resource binding)
            if enable_audience and resource_uri:
                is_valid = auth_data.is_valid_for_resource(resource_uri)
            else:
                # Legacy behavior: only check expiry
                is_valid = auth_data.expires_at > datetime.now(UTC)

            # Token expired or invalid - try refresh
            if not is_valid:
                if enable_refresh and auth_data.refresh_token and resource_uri:
                    logger.info(
                        f"Token expired/invalid for {server_config.name}, attempting refresh"
                    )

                    try:
                        # Initialize OAuth client
                        oauth_client = OAuthClient()

                        # Discover Protected Resource Metadata (RFC 9728) for HTTP MCP
                        has_prm = False
                        if server_config.url:  # Only for HTTP MCP servers
                            try:
                                cache = oauth_client.metadata_cache
                                prm = await cache.fetch_protected_resource_metadata(
                                    server_config.url
                                )
                                has_prm = prm is not None
                                if prm:
                                    logger.debug(
                                        f"Discovered PRM for {server_config.name} "
                                        "during token refresh"
                                    )
                            except Exception as e:
                                logger.debug(f"PRM discovery failed (optional): {e}")
                                has_prm = False

                        # Determine if resource param should be included (MCP spec 2025-06-18)
                        include_resource = oauth_client.should_include_resource_param(
                            protocol_version=server_config.protocol_version, has_prm=has_prm
                        )

                        # Discover token endpoint from authorization server metadata (RFC 8414)
                        token_endpoint = None
                        try:
                            metadata = await oauth_client.metadata_cache.fetch_auth_server_metadata(
                                server_config.auth_server
                            )
                            token_endpoint = str(metadata.token_endpoint)
                            logger.debug(f"Discovered token endpoint for refresh: {token_endpoint}")
                        except Exception as e:
                            logger.debug(f"Failed to discover token endpoint: {e}. Using fallback.")
                            token_endpoint = f"{server_config.auth_server.rstrip('/')}/token"

                        # Build refresh request
                        refresh_request = RefreshTokenRequest(
                            token_endpoint=token_endpoint,
                            refresh_token=auth_data.refresh_token,
                            resource=resource_uri
                            if include_resource
                            else None,  # Conditional per protocol version
                            client_id=server_config.oauth_client_id
                            or app_config.get("TA_OAUTH_CLIENT_NAME"),
                            client_secret=server_config.oauth_client_secret,
                            requested_scopes=auth_data.scopes,  # For scope validation
                        )

                        # Refresh token
                        token_response = await oauth_client.refresh_access_token(refresh_request)

                        # Update auth data with new tokens
                        auth_data.access_token = token_response.access_token
                        auth_data.expires_at = datetime.now(UTC) + timedelta(
                            seconds=token_response.expires_in
                        )
                        auth_data.issued_at = datetime.now(UTC)

                        # Handle refresh token rotation (OAuth 2.1)
                        if token_response.refresh_token:
                            auth_data.refresh_token = token_response.refresh_token
                            logger.debug(f"Refresh token rotated for {server_config.name}")

                        # Update audience if provided
                        if token_response.aud:
                            auth_data.audience = token_response.aud

                        # Store updated auth data
                        auth_storage.store(user_id, composite_key, auth_data)

                        logger.info(f"Successfully refreshed token for {server_config.name}")

                    except httpx.HTTPStatusError as http_error:
                        # Handle 401 WWW-Authenticate challenges
                        if http_error.response.status_code == 401:
                            challenge = OAuthErrorHandler.handle_401_response(
                                dict(http_error.response.headers)
                            )

                            if challenge and OAuthErrorHandler.should_reauthorize(challenge):
                                logger.info(
                                    f"Received 401 with WWW-Authenticate challenge "
                                    f"during token refresh for {server_config.name}. "
                                    f"Error: {challenge.error}, "
                                    f"Description: {challenge.error_description}"
                                )
                                # Extract required scopes from challenge or use configured
                                required_scopes = (
                                    challenge.scopes if challenge.scopes else server_config.scopes
                                )
                                err_msg = challenge.error_description or challenge.error
                                raise AuthRequiredError(
                                    server_name=server_config.name,
                                    auth_server=server_config.auth_server,
                                    scopes=required_scopes,
                                    message=f"Token rejected by server: {err_msg}",
                                ) from http_error

                        # Re-raise other HTTP errors
                        logger.error(
                            f"HTTP error during token refresh for "
                            f"{server_config.name}: {http_error}"
                        )
                        raise AuthRequiredError(
                            server_name=server_config.name,
                            auth_server=server_config.auth_server,
                            scopes=server_config.scopes,
                            message=f"Token refresh HTTP error: {http_error}",
                        ) from http_error

                    except Exception as refresh_error:
                        logger.error(
                            f"Token refresh failed for {server_config.name}: {refresh_error}"
                        )
                        # Refresh failed - require re-authentication
                        raise AuthRequiredError(
                            server_name=server_config.name,
                            auth_server=server_config.auth_server,
                            scopes=server_config.scopes,
                            message=f"Token refresh failed for '{server_config.name}'. "
                            "Re-authentication required.",
                        ) from refresh_error
                else:
                    # Refresh not enabled or no refresh token
                    logger.warning(
                        f"Token expired for {server_config.name} and refresh not available"
                    )
                    raise AuthRequiredError(
                        server_name=server_config.name,
                        auth_server=server_config.auth_server,
                        scopes=server_config.scopes,
                        message=f"Token expired for '{server_config.name}'",
                    )

            # Token is valid (or was successfully refreshed)
            headers["Authorization"] = f"{auth_data.token_type} {auth_data.access_token}"
            logger.info(f"Resolved auth headers for MCP server: {server_config.name}")

        except AuthRequiredError:
            # Re-raise auth errors
            raise
        except Exception as e:
            logger.error(f"Failed to resolve auth for MCP server {server_config.name}: {e}")
            raise AuthRequiredError(
                server_name=server_config.name,
                auth_server=server_config.auth_server if server_config.auth_server else "unknown",
                scopes=server_config.scopes if server_config.scopes else [],
                message=f"Auth resolution failed: {e}",
            ) from e

    # Debug logging: show what headers we're about to send
    safe_headers = {}
    for k, v in headers.items():
        if k.lower() == "authorization":
            # Redact token but show format
            if v.startswith("Bearer "):
                safe_headers[k] = "Bearer [REDACTED]"
            elif v.startswith("ghp_"):
                safe_headers[k] = "ghp_[REDACTED]"
            else:
                safe_headers[k] = "[REDACTED]"
        else:
            safe_headers[k] = v
    logger.info(f"Resolved headers for {server_config.name}: {safe_headers}")

    return headers


async def revoke_mcp_server_tokens(
    server_config: McpServerConfig, user_id: str = "default"
) -> None:
    """
    Revoke all tokens for an MCP server.

    Useful when:
    - User logs out
    - Security incident detected
    - Server access no longer needed

    Args:
        server_config: MCP server configuration
        user_id: User ID for token lookup

    Raises:
        Exception: If revocation fails
    """
    from ska_utils import AppConfig

    from sk_agents.auth.oauth_client import OAuthClient

    if not server_config.auth_server or not server_config.scopes:
        logger.debug(f"Server {server_config.name} has no OAuth config, skipping revocation")
        return

    app_config = AppConfig()
    auth_storage_factory = AuthStorageFactory(app_config)
    auth_storage = auth_storage_factory.get_auth_storage_manager()
    oauth_client = OAuthClient()

    # Retrieve stored tokens
    composite_key = build_auth_storage_key(server_config.auth_server, server_config.scopes)
    auth_data = auth_storage.retrieve(user_id, composite_key)

    if not auth_data or not isinstance(auth_data, OAuth2AuthData):
        logger.debug(f"No tokens found for {server_config.name}, skipping revocation")
        return

    try:
        # Discover revocation endpoint
        metadata = await oauth_client.metadata_cache.fetch_auth_server_metadata(
            server_config.auth_server
        )

        if not metadata.revocation_endpoint:
            logger.warning(
                f"No revocation_endpoint discovered for {server_config.auth_server}. "
                f"Cannot revoke tokens."
            )
            return

        # Revoke access token
        await oauth_client.revoke_token(
            token=auth_data.access_token,
            revocation_endpoint=str(metadata.revocation_endpoint),
            client_id=server_config.oauth_client_id or app_config.get("TA_OAUTH_CLIENT_NAME"),
            client_secret=server_config.oauth_client_secret,
            token_type_hint="access_token",
        )

        # Revoke refresh token if present
        if auth_data.refresh_token:
            await oauth_client.revoke_token(
                token=auth_data.refresh_token,
                revocation_endpoint=str(metadata.revocation_endpoint),
                client_id=server_config.oauth_client_id or app_config.get("TA_OAUTH_CLIENT_NAME"),
                client_secret=server_config.oauth_client_secret,
                token_type_hint="refresh_token",
            )

        # Remove from storage
        auth_storage.delete(user_id, composite_key)

        logger.info(f"Successfully revoked and removed tokens for {server_config.name}")

    except Exception as e:
        logger.error(f"Failed to revoke tokens for {server_config.name}: {e}")
        raise


async def create_mcp_session_with_retry(
    server_config: McpServerConfig,
    connection_stack: AsyncExitStack,
    user_id: str = "default",
    max_retries: int = 3,
    mcp_session_id: str | None = None,
    on_stale_session: Callable[[str], Awaitable[None]] | None = None,
    app_config: AppConfig | None = None,
) -> tuple[ClientSession, Callable[[], str | None]]:
    """
    Create MCP session with retry logic for transient failures.

    This function wraps create_mcp_session with exponential backoff retry logic
    to handle transient network issues and temporary server unavailability.

    Args:
        server_config: MCP server configuration
        connection_stack: AsyncExitStack for resource management
        user_id: User ID for authentication
        max_retries: Maximum number of retry attempts (default: 3)

    Returns:
        ClientSession: Initialized MCP session

    Raises:
        ConnectionError: If all retry attempts fail
        ValueError: If server configuration is invalid
    """
    last_error = None

    for attempt in range(max_retries):
        try:
            session, get_session_id = await create_mcp_session(
                server_config,
                connection_stack,
                user_id,
                mcp_session_id=mcp_session_id,
                app_config=app_config,
            )

            # If we succeed after retries, log it
            if attempt > 0:
                logger.info(
                    f"Successfully connected to MCP server '{server_config.name}' "
                    f"after {attempt + 1} attempt(s)"
                )

            return session, get_session_id

        except (ConnectionError, TimeoutError, OSError) as e:
            last_error = e

            # If the first attempt with a stored session id fails, clear and retry fresh once
            if mcp_session_id and on_stale_session:
                try:
                    await on_stale_session(mcp_session_id)
                except Exception:
                    logger.debug("Failed to clear stale MCP session id during retry path")
                mcp_session_id = None

            # Don't retry on the last attempt
            if attempt < max_retries - 1:
                backoff_seconds = 2**attempt  # 1s, 2s, 4s
                logger.warning(
                    f"MCP connection attempt {attempt + 1}/{max_retries} failed for "
                    f"'{server_config.name}': {e}. Retrying in {backoff_seconds}s..."
                )
                await asyncio.sleep(backoff_seconds)
            else:
                # Final attempt failed
                logger.error(
                    f"Failed to connect to MCP server '{server_config.name}' "
                    f"after {max_retries} attempts"
                )

        except Exception as e:
            # If failure might be due to stale session id, clear once then re-raise
            if mcp_session_id and on_stale_session:
                try:
                    await on_stale_session(mcp_session_id)
                except Exception:
                    logger.debug("Failed to clear stale MCP session id during retry path")
            logger.error(
                f"Non-retryable error connecting to MCP server '{server_config.name}': {e}"
            )
            raise

    # All retries exhausted
    raise ConnectionError(
        f"Failed to connect to MCP server '{server_config.name}' after {max_retries} attempts. "
        f"Last error: {last_error}"
    ) from last_error


async def create_mcp_session(
    server_config: McpServerConfig,
    connection_stack: AsyncExitStack,
    user_id: str = "default",
    mcp_session_id: str | None = None,
    app_config: AppConfig | None = None,
) -> tuple[ClientSession, Callable[[], str | None]]:
    """Create MCP session using SDK transport factories."""
    transport_type = server_config.transport

    if transport_type == "stdio":
        from mcp.client.stdio import stdio_client

        server_params = StdioServerParameters(
            command=server_config.command, args=server_config.args, env=server_config.env or {}
        )

        read, write = await connection_stack.enter_async_context(stdio_client(server_params))
        session = await connection_stack.enter_async_context(ClientSession(read, write))

        await initialize_mcp_session(
            session,
            server_config.name,
            protocol_version=server_config.protocol_version or "2025-11-25",
        )
        return session, (lambda: None)

    elif transport_type == "http":
        # Resolve auth headers for HTTP transport
        resolved_headers = await resolve_server_auth_headers(
            server_config, user_id, app_config=app_config
        )

        # Try streamable HTTP first (preferred), fall back to SSE
        try:
            from mcp.client.streamable_http import streamablehttp_client

            # Create custom httpx client factory if SSL verification is disabled
            httpx_client_factory = None
            if getattr(server_config, "verify_ssl", True) is False:
                logger.warning(
                    f"SSL verification disabled for MCP server '{server_config.name}'. "
                    f"Creating custom httpx client factory with verify=False"
                )

                def create_insecure_http_client(
                    headers: dict[str, str] | None = None,
                    timeout: httpx.Timeout | None = None,
                    auth: httpx.Auth | None = None,
                ) -> httpx.AsyncClient:
                    """Create httpx client with SSL verification disabled."""
                    logger.debug(
                        f"Creating insecure httpx client for {server_config.name} with verify=False"
                    )
                    kwargs: dict[str, Any] = {
                        "follow_redirects": True,
                        "verify": False,  # Disable SSL verification
                    }
                    if timeout is None:
                        kwargs["timeout"] = httpx.Timeout(30.0)
                    else:
                        kwargs["timeout"] = timeout
                    if headers is not None:
                        kwargs["headers"] = headers
                    if auth is not None:
                        kwargs["auth"] = auth

                    logger.debug(f"httpx.AsyncClient kwargs: {kwargs}")
                    return httpx.AsyncClient(**kwargs)

                httpx_client_factory = create_insecure_http_client

            # Build kwargs for streamablehttp_client
            headers_with_session = resolved_headers.copy()
            if mcp_session_id:
                headers_with_session["Mcp-Session-Id"] = mcp_session_id

            client_kwargs = {
                "url": server_config.url,
                "headers": headers_with_session,
                "timeout": server_config.timeout or 30.0,
                "sse_read_timeout": server_config.sse_read_timeout or 300.0,
            }
            if httpx_client_factory is not None:
                client_kwargs["httpx_client_factory"] = httpx_client_factory
                logger.info(
                    f"Passing custom httpx_client_factory to streamablehttp_client "
                    f"for {server_config.name}"
                )
            else:
                logger.debug(
                    f"No custom httpx_client_factory for {server_config.name}, "
                    "using default SSL verification"
                )

            # Use streamable HTTP transport
            read, write, get_session_id = await connection_stack.enter_async_context(
                streamablehttp_client(**client_kwargs)
            )
            session = await connection_stack.enter_async_context(ClientSession(read, write))

            await initialize_mcp_session(
                session,
                server_config.name,
                protocol_version=server_config.protocol_version or "2025-11-25",
            )
            return session, get_session_id

        except ImportError as err:
            raise NotImplementedError(
                "HTTP transport is not available. Please install the MCP SDK with HTTP support"
            ) from err
            # # Fall back to SSE transport if streamable HTTP not available
            # try:
            #     from mcp.client.sse import sse_client

            #     read, write = await connection_stack.enter_async_context(
            #         sse_client(
            #             url=server_config.url,
            #             headers=resolved_headers,
            #             timeout=server_config.timeout or 30.0,
            #             sse_read_timeout=server_config.sse_read_timeout or 300.0
            #         )
            #     )
            #     session = await connection_stack.enter_async_context(
            #         ClientSession(read, write)
            #     )

            #     return session

            # except ImportError:
            #     raise NotImplementedError(
            #         "HTTP transport is not available. "
            #         "Please install the MCP SDK with HTTP support: "
            #         "pip install 'mcp[http]' or 'mcp[sse]'"
            #     )
    else:
        raise ValueError(f"Unsupported transport type: {transport_type}")


def get_transport_info(server_config: McpServerConfig) -> str:
    """Get transport info for logging."""
    if server_config.transport == "stdio":
        # Sanitize sensitive arguments
        safe_args = []
        for arg in server_config.args:
            if any(
                keyword in arg.lower() for keyword in ["token", "key", "secret", "password", "auth"]
            ):
                safe_args.append("[REDACTED]")
            else:
                safe_args.append(arg)
        return f"stdio:{server_config.command} {' '.join(safe_args)}"
    elif server_config.transport == "http":
        # Sanitize URL for logging
        url = server_config.url or ""
        if "?" in url:
            url = url.split("?")[0]
        return f"http:{url}"
    else:
        return f"{server_config.transport}:unknown"


class McpConnectionManager:
    """
    Request-scoped connection manager for MCP servers.

    Manages MCP connections within a single agent invoke() request scope:
    - Lazy connection establishment (connect on first tool call per server)
    - Connection reuse within the request (all tools on same server share connection)
    - Automatic cleanup at request end
    - Session ID persistence via state manager for cross-request continuity

    Lifecycle:
        1. Created at start of invoke() request
        2. Connections created lazily when first tool from server is called
        3. Connections reused for all subsequent tool calls in same request
        4. Cleanup at end of invoke() - close connections, persist session IDs

    Usage:
        async with McpConnectionManager(servers, user_id, ...) as conn_mgr:
            session = await conn_mgr.get_or_create_session(server_name)
            result = await session.call_tool(tool_name, args)
    """

    def __init__(
        self,
        server_configs: dict[str, McpServerConfig],
        user_id: str,
        session_id: str,
        state_manager=None,  # McpStateManager for session ID persistence
        app_config: AppConfig = None,
    ):
        self._server_configs = server_configs
        self._user_id = user_id
        self._session_id = session_id
        self._state_manager = state_manager
        self._app_config = app_config

        # Active connections (created lazily)
        self._sessions: dict[str, ClientSession] = {}
        self._get_session_id_callbacks: dict[str, Callable[[], str | None]] = {}
        self._connection_stack: AsyncExitStack | None = None

        # Stored session IDs from previous requests
        self._stored_session_ids: dict[str, str] = {}

    async def __aenter__(self) -> "McpConnectionManager":
        """Enter context - initialize and load stored session IDs."""
        self._connection_stack = AsyncExitStack()
        await self._connection_stack.__aenter__()

        # Pre-load stored session IDs for all configured servers
        if self._state_manager:
            for server_name in self._server_configs:
                try:
                    stored_id = await self._state_manager.get_mcp_session(
                        self._user_id, self._session_id, server_name
                    )
                    if stored_id:
                        self._stored_session_ids[server_name] = stored_id
                        logger.debug(f"Loaded stored MCP session for {server_name}")
                except Exception as e:
                    logger.debug(f"Could not load stored session for {server_name}: {e}")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Exit context - persist session IDs and cleanup connections."""
        try:
            # Persist session IDs for servers that were connected
            if self._state_manager:
                for server_name, get_session_id in self._get_session_id_callbacks.items():
                    try:
                        current_id = get_session_id() if get_session_id else None
                        if current_id:
                            await self._state_manager.store_mcp_session(
                                self._user_id, self._session_id, server_name, current_id
                            )
                            logger.debug(f"Persisted MCP session for {server_name}")
                    except Exception as e:
                        logger.warning(f"Failed to persist MCP session for {server_name}: {e}")
        finally:
            # Close all connections
            if self._connection_stack:
                try:
                    await self._connection_stack.__aexit__(exc_type, exc_val, exc_tb)
                except RuntimeError as e:
                    # Handle anyio task affinity errors gracefully.
                    # This can happen when the connection manager is used across
                    # recursive handler calls that change the async task context.
                    # The MCP SDK's streamablehttp_client uses anyio.create_task_group()
                    # which requires entering/exiting in the same async task.
                    err_str = str(e)
                    if "cancel scope" in err_str and "different task" in err_str:
                        logger.warning(
                            f"MCP cleanup encountered task affinity issue (non-fatal): {e}"
                        )
                    else:
                        raise
            self._sessions.clear()
            self._get_session_id_callbacks.clear()

    async def get_or_create_session(self, server_name: str) -> ClientSession:
        """
        Get existing session or create new one for server (lazy connection).

        Args:
            server_name: Name of the MCP server

        Returns:
            Active MCP ClientSession for the server
        """
        if server_name in self._sessions:
            logger.debug(f"Reusing MCP session for {server_name}")
            return self._sessions[server_name]

        server_config = self._server_configs.get(server_name)
        if not server_config:
            raise ValueError(f"Unknown MCP server: {server_name}")

        if not self._connection_stack:
            raise RuntimeError("McpConnectionManager must be used as async context manager")

        stored_session_id = self._stored_session_ids.get(server_name)

        session, get_session_id = await create_mcp_session_with_retry(
            server_config,
            self._connection_stack,
            self._user_id,
            mcp_session_id=stored_session_id,
            on_stale_session=self._create_stale_handler(server_name),
            app_config=self._app_config,
        )

        self._sessions[server_name] = session
        self._get_session_id_callbacks[server_name] = get_session_id
        logger.info(f"Created MCP session for {server_name}")
        return session

    def _create_stale_handler(self, server_name: str) -> Callable[[str], Awaitable[None]]:
        """Create callback to handle stale session ID."""

        async def handler(stale_id: str):
            logger.info(f"Clearing stale MCP session for {server_name}")
            if self._state_manager:
                try:
                    await self._state_manager.clear_mcp_session(
                        self._user_id, self._session_id, server_name, expected_session_id=stale_id
                    )
                except Exception as e:
                    logger.debug(f"Failed to clear stale session: {e}")
            self._stored_session_ids.pop(server_name, None)

        return handler

    def has_active_session(self, server_name: str) -> bool:
        """Check if server has an active session in this request."""
        return server_name in self._sessions

    def get_active_servers(self) -> list[str]:
        """Get list of servers with active sessions."""
        return list(self._sessions.keys())


class McpTool:
    """
    Stateless wrapper for MCP tools to make them compatible with Semantic Kernel.

    This class stores the server configuration and tool metadata, but does NOT
    store active connections. Each invocation creates a temporary connection.
    """

    def __init__(
        self,
        tool_name: str,
        description: str,
        input_schema: dict[str, Any],
        output_schema: dict[str, Any] | None,
        server_config: "McpServerConfig",
        server_name: str,
    ):
        """
        Initialize stateless MCP tool.

        Args:
            tool_name: Name of the MCP tool
            description: Tool description
            input_schema: JSON schema for tool inputs
            output_schema: JSON schema for tool outputs (optional)
            server_config: MCP server configuration (for reconnection)
            server_name: Name of the MCP server
        """
        self.tool_name = tool_name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.server_config = server_config
        self.server_name = server_name
        self.app_config: AppConfig | None = None  # Set via McpPlugin at instantiation time

    async def invoke(
        self,
        connection_manager: "McpConnectionManager",
        **kwargs,
    ) -> str:
        """
        Invoke the MCP tool using a request-scoped connection manager.

        Args:
            connection_manager: Request-scoped connection manager for connection reuse
            **kwargs: Tool arguments

        Returns:
            Tool execution result as string

        Raises:
            ValueError: If connection_manager is not provided
            RuntimeError: If tool execution fails
        """
        if not connection_manager:
            raise ValueError(
                f"connection_manager is required for MCP tool invocation. "
                f"Tool '{self.tool_name}' cannot be invoked without a connection manager."
            )

        try:
            if self.input_schema:
                self._validate_inputs(kwargs)

            logger.debug(f"Executing MCP tool: {self.server_name}.{self.tool_name}")
            session = await connection_manager.get_or_create_session(self.server_name)
            result = await session.call_tool(self.tool_name, kwargs)
            parsed = self._parse_result(result)
            logger.debug(f"MCP tool {self.tool_name} completed successfully")
            return parsed

        except ValueError:
            # Re-raise validation errors as-is
            raise
        except Exception as e:
            logger.error(f"Error invoking MCP tool {self.tool_name}: {e}")

            error_msg = str(e).lower()
            if "timeout" in error_msg:
                raise RuntimeError(
                    f"MCP tool '{self.tool_name}' timed out. Check server responsiveness."
                ) from e
            elif "connection" in error_msg:
                raise RuntimeError(
                    f"MCP tool '{self.tool_name}' connection failed. Check server availability."
                ) from e
            else:
                raise RuntimeError(f"MCP tool '{self.tool_name}' failed: {e}") from e

    def _parse_result(self, result: Any) -> str:
        """Parse MCP result into string format."""
        if hasattr(result, "content"):
            if isinstance(result.content, list) and len(result.content) > 0:
                return (
                    str(result.content[0].text)
                    if hasattr(result.content[0], "text")
                    else str(result.content[0])
                )
            return str(result.content)
        elif hasattr(result, "text"):
            return result.text
        else:
            return str(result)

    def _validate_inputs(self, kwargs: dict[str, Any]) -> None:
        """Basic input validation against the tool's JSON schema."""
        if not isinstance(self.input_schema, dict):
            return

        properties = self.input_schema.get("properties", {})
        required = self.input_schema.get("required", [])

        # Check required parameters
        for req_param in required:
            if req_param not in kwargs:
                raise ValueError(
                    f"Missing required parameter '{req_param}' for tool '{self.tool_name}'"
                )

        # Warn about unexpected parameters
        for param in kwargs:
            if param not in properties:
                logger.warning(f"Unexpected parameter '{param}' for tool '{self.tool_name}'")


class McpPlugin(BasePlugin):
    """
    Plugin wrapper that holds MCP tools for Semantic Kernel integration.

    This plugin creates kernel functions with proper type annotations from MCP JSON schemas,
    allowing Semantic Kernel to expose full parameter information to the LLM.

    MCP-Specific Design Note:
    -------------------------
    MCP plugins require both user_id and connection_manager:

    1. **Per-User Authentication**: MCP tools connect to external services that require OAuth2
       authentication. Tokens are stored per-user in AuthStorage.

    2. **Connection Reuse**: All tool calls within a request share connections via the
       connection_manager, reducing overhead from per-tool-call to per-request per-server.

    Args:
        tools: List of MCP tools discovered from the server
        server_name: Name of the MCP server (used for logging and namespacing)
        user_id: User ID for OAuth2 token resolution (REQUIRED)
        connection_manager: Request-scoped connection manager (REQUIRED)
        authorization: Optional standard authorization header (rarely used with MCP)
        extra_data_collector: Optional collector for extra response data

    Raises:
        ValueError: If user_id or connection_manager is not provided

    Example:
        >>> async with McpConnectionManager(configs, user_id, session_id) as conn_mgr:
        ...     plugin_instance = plugin_class(
        ...         user_id="user123",
        ...         connection_manager=conn_mgr,
        ...         extra_data_collector=collector
        ...     )
        ...     kernel.add_plugin(plugin_instance, "mcp_github")
    """

    def __init__(
        self,
        tools: list[McpTool],
        server_name: str,
        user_id: str,
        connection_manager: "McpConnectionManager",
        authorization: str | None = None,
        extra_data_collector=None,
    ):
        if not user_id:
            raise ValueError(
                "MCP plugins require a user_id for per-request OAuth2 token resolution."
            )
        if not connection_manager:
            raise ValueError(
                "MCP plugins require a connection_manager for request-scoped connection reuse. "
                "Create one using McpConnectionManager and pass it to the plugin."
            )

        super().__init__(authorization, extra_data_collector)
        self.tools = tools
        self.server_name = server_name
        self.user_id = user_id
        self.connection_manager = connection_manager

        # Dynamically add kernel functions for each tool
        for tool in tools:
            self._add_tool_function(tool)

    def _add_tool_function(self, tool: McpTool):
        """
        Add a tool as a kernel function with proper type annotations.

        Converts MCP JSON schema to Python type hints so SK can expose
        full parameter information to the LLM.
        """

        # Create a closure that captures the specific tool instance
        def create_tool_function(captured_tool: McpTool):
            # Create unique tool name to avoid collisions
            function_name = f"{self.server_name}_{captured_tool.tool_name}"

            @kernel_function(
                name=function_name,
                description=f"[{self.server_name}] {captured_tool.description}",
            )
            async def tool_function(**kwargs):
                return await captured_tool.invoke(
                    connection_manager=self.connection_manager,
                    **kwargs,
                )

            # CRITICAL FIX: Override __kernel_function_parameters__ after decoration
            # This is the CORRECT way to set function parameters in Semantic Kernel
            # The decorator has already read inspect.signature() (which only sees **kwargs),
            # but we can override the parameters it uses to build the LLM schema
            tool_function.__kernel_function_parameters__ = self._build_sk_parameters(
                captured_tool.input_schema
            )

            return tool_function

        # Create the function and set as attribute
        tool_function = create_tool_function(tool)

        # Sanitize tool name for Python attribute
        attr_name = self._sanitize_name(f"{self.server_name}_{tool.tool_name}")

        setattr(self, attr_name, tool_function)

    def _build_sk_parameters(self, input_schema: dict[str, Any]) -> list[dict[str, Any]]:
        """
        Build Semantic Kernel parameter dictionaries from MCP JSON schema.

        This creates the parameter metadata in the format expected by
        KernelParameterMetadata, which Semantic Kernel uses to build
        the schema sent to the LLM.

        This is the CORRECT way to override function parameters in SK -
        by setting __kernel_function_parameters__ after decoration.

        Args:
            input_schema: MCP tool's JSON schema for inputs

        Returns:
            List of parameter dictionaries for SK
        """
        if not input_schema or not isinstance(input_schema, dict):
            return []

        properties = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        params = []

        for param_name, param_schema in properties.items():
            if not isinstance(param_schema, dict):
                continue

            # Build parameter dict in SK format
            param_dict = {
                "name": param_name,
                "description": param_schema.get("description", ""),
                "is_required": param_name in required,
                "type_": param_schema.get("type", "string"),  # JSON type string
                "default_value": param_schema.get("default", None),
                "schema_data": param_schema,  # Full JSON schema sent to LLM
            }

            # Add Python type object for better type handling
            json_type = param_schema.get("type", "string")
            param_dict["type_object"] = self._json_type_to_python(json_type)

            params.append(param_dict)

        return params

    @staticmethod
    def _json_type_to_python(json_type: str) -> type:
        """
        Map JSON schema types to Python types.

        Args:
            json_type: JSON schema type string

        Returns:
            Corresponding Python type
        """
        type_map = {
            "string": str,
            "number": float,
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        return type_map.get(json_type, str)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize name for Python attribute."""
        sanitized = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        if not sanitized[0].isalpha() and sanitized[0] != "_":
            sanitized = f"tool_{sanitized}"
        return sanitized
