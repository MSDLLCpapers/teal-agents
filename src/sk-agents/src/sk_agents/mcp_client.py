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
from typing import Any, Dict, List, Optional, Callable, Awaitable
from contextlib import AsyncExitStack
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from mcp import ClientSession, StdioServerParameters
from semantic_kernel.functions import kernel_function
from semantic_kernel.kernel import Kernel

from sk_agents.ska_types import BasePlugin
from sk_agents.tealagents.v1alpha1.config import McpServerConfig
from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.plugin_catalog.models import Governance, GovernanceOverride, Oauth2PluginAuth, PluginTool
from sk_agents.plugin_catalog.plugin_catalog_factory import PluginCatalogFactory


logger = logging.getLogger(__name__)


def build_auth_storage_key(auth_server: str, scopes: List[str]) -> str:
    """Create deterministic key for storing OAuth tokens in AuthStorage."""
    normalized_scopes = '|'.join(sorted(scopes)) if scopes else ''
    return f"{auth_server}|{normalized_scopes}" if normalized_scopes else auth_server


def get_package_version() -> str:
    """Get package version for MCP client identification."""
    try:
        from importlib.metadata import version
        return version('sk-agents')
    except Exception:
        return '1.0.0'  # Fallback version


def validate_mcp_sdk_version() -> None:
    """
    Validate MCP SDK version compatibility.

    Logs warnings if the installed MCP SDK version is too old to support all features.
    """
    try:
        import mcp
        version_str = getattr(mcp, '__version__', '0.0.0')

        # Parse version components
        try:
            from packaging import version as pkg_version
            installed_version = pkg_version.parse(version_str)
            required_version = pkg_version.parse("1.13.1")

            if installed_version < required_version:
                logger.warning(
                    f"MCP SDK version {version_str} detected. "
                    f"Recommended: >= 1.13.1 for full HTTP transport support. "
                    f"Some features may not be available."
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
    server_info_obj: Any = None
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
        # Step 1: Send initialize request
        init_result = await session.initialize(
            protocol_version="2025-03-26",
            client_info={
                "name": "teal-agents",
                "version": get_package_version()
            },
            capabilities={
                "roots": {"listChanged": False},
                "sampling": {},
                "experimental": {}
            }
        )

        logger.info(
            f"MCP session initialized for '{server_name}': "
            f"server={getattr(init_result, 'server_info', 'unknown')}, "
            f"protocol={getattr(init_result, 'protocol_version', 'unknown')}"
        )

        # Step 2: Send initialized notification (MCP protocol requirement)
        # Per MCP spec: "After successful initialization, the client MUST send
        # an initialized notification to indicate it is ready to begin normal operations."
        try:
            # The MCP Python SDK may use different method names
            # Try common variations
            if hasattr(session, 'send_initialized'):
                await session.send_initialized()
                logger.debug(f"Sent initialized notification to '{server_name}'")
            elif hasattr(session, 'initialized'):
                await session.initialized()
                logger.debug(f"Sent initialized notification to '{server_name}'")
            else:
                logger.warning(
                    f"Could not find initialized notification method for '{server_name}'. "
                    f"MCP SDK may not support this yet. Session may not function correctly."
                )
        except Exception as notify_error:
            # Don't fail the entire initialization if notification fails
            # Some SDK versions may not support this yet
            logger.warning(
                f"Failed to send initialized notification to '{server_name}': {notify_error}. "
                f"Proceeding anyway, but server may not function correctly."
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
        # Try to send shutdown notification if supported
        if hasattr(session, 'send_shutdown'):
            await session.send_shutdown()
            logger.debug(f"Sent graceful shutdown to MCP server: {server_name}")
        elif hasattr(session, 'shutdown'):
            await session.shutdown()
            logger.debug(f"Sent graceful shutdown to MCP server: {server_name}")
        else:
            logger.debug(f"MCP SDK does not support shutdown notification for: {server_name}")
    except Exception as e:
        # Shutdown failures are non-critical - log and continue with cleanup
        logger.debug(f"Graceful shutdown failed for {server_name} (non-critical): {e}")


def map_mcp_annotations_to_governance(annotations: Dict[str, Any], tool_description: str = "") -> Governance:
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
        if any(keyword in description_lower for keyword in [
            "http", "https", "api", "network", "request", "fetch", "download", "upload",
            "url", "web", "internet", "remote", "curl", "wget"
        ]):
            requires_hitl = True
            cost = "high"
            data_sensitivity = "sensitive"

        # File system access indicators
        elif any(keyword in description_lower for keyword in [
            "file", "directory", "write", "delete", "create", "modify", "save",
            "remove", "mkdir", "rmdir", "chmod", "move", "copy"
        ]):
            requires_hitl = True
            cost = "medium" if not destructive_hint else "high"
            data_sensitivity = "proprietary"

        # Code execution indicators
        elif any(keyword in description_lower for keyword in [
            "execute", "run", "command", "shell", "bash", "script", "eval", "exec"
        ]):
            requires_hitl = True
            cost = "high"
            data_sensitivity = "sensitive"

        # Database/storage access
        elif any(keyword in description_lower for keyword in [
            "database", "sql", "query", "insert", "update", "delete", "drop"
        ]):
            requires_hitl = True
            cost = "high"
            data_sensitivity = "sensitive"

    return Governance(
        requires_hitl=requires_hitl,
        cost=cost,
        data_sensitivity=data_sensitivity
    )


def apply_trust_level_governance(base_governance: Governance, trust_level: str, tool_description: str = "") -> Governance:
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
        logger.debug(f"Applying untrusted server governance: forcing HITL")
        return Governance(
            requires_hitl=True,
            cost="high",
            data_sensitivity="sensitive"
        )
    elif trust_level == "sandboxed":
        # Require HITL unless explicitly marked as safe
        # Sandboxed servers get elevated restrictions
        logger.debug(f"Applying sandboxed server governance: elevated restrictions")
        return Governance(
            requires_hitl=True,  # Force HITL for sandboxed servers
            cost=base_governance.cost if base_governance.cost != "low" else "medium",  # Elevate cost
            data_sensitivity=base_governance.data_sensitivity
        )
    else:  # trusted
        # For trusted servers, use base governance but still enforce safety on high-risk operations
        # This provides defense-in-depth even for trusted sources

        # Check if tool description indicates high-risk operations
        # Even for trusted servers, certain operations should require HITL
        description_lower = tool_description.lower()
        high_risk_operations = [
            'delete', 'remove', 'drop', 'truncate', 'destroy', 'kill',
            'execute', 'exec', 'eval', 'run command', 'shell',
            'system', 'sudo', 'admin', 'root'
        ]

        has_high_risk = any(keyword in description_lower for keyword in high_risk_operations)

        if has_high_risk and not base_governance.requires_hitl:
            # Override for high-risk operations even on trusted servers
            logger.debug(
                f"Trusted server tool has high-risk indicators in description, "
                f"enforcing HITL despite trust level"
            )
            return Governance(
                requires_hitl=True,  # Override to require HITL
                cost="high" if base_governance.cost != "high" else base_governance.cost,
                data_sensitivity=base_governance.data_sensitivity
            )

        # For non-high-risk operations on trusted servers, use base governance
        logger.debug(f"Applying trusted server governance: using base governance")
        return base_governance


def apply_governance_overrides(base_governance: Governance, tool_name: str, overrides: Optional[Dict[str, GovernanceOverride]]) -> Governance:
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
        requires_hitl=override.requires_hitl if override.requires_hitl is not None else base_governance.requires_hitl,
        cost=override.cost if override.cost is not None else base_governance.cost,
        data_sensitivity=override.data_sensitivity if override.data_sensitivity is not None else base_governance.data_sensitivity
    )


def resolve_server_auth_headers(server_config: McpServerConfig, user_id: str = "default") -> Dict[str, str]:
    """
    Resolve authentication headers for MCP server connection.

    Args:
        server_config: MCP server configuration
        user_id: User ID for auth lookup

    Returns:
        Dict[str, str]: Headers to use for server connection
    """
    headers = {}

    # Start with any manually configured headers (legacy support)
    if server_config.headers:
        for header_key, header_value in server_config.headers.items():
            if header_key.lower() == "authorization":
                logger.warning(
                    "Ignoring static Authorization header configured for MCP server %s. "
                    "Use OAuth-based auth_server/scopes instead.",
                    server_config.name
                )
                continue
            headers[header_key] = header_value

    # If server has auth configuration, resolve tokens using existing auth system
    if server_config.auth_server and server_config.scopes:
        try:
            # Use AuthStorageFactory directly - no wrapper needed
            from ska_utils import AppConfig
            app_config = AppConfig()
            auth_storage_factory = AuthStorageFactory(app_config)
            auth_storage = auth_storage_factory.get_auth_storage_manager()

            # Generate composite key for OAuth2 token lookup
            composite_key = build_auth_storage_key(server_config.auth_server, server_config.scopes)

            # Retrieve stored auth data
            auth_data = auth_storage.retrieve(user_id, composite_key)

            if auth_data and isinstance(auth_data, OAuth2AuthData):
                # Check if token is still valid
                from datetime import datetime
                if auth_data.expires_at > datetime.utcnow():
                    # Add authorization header
                    headers["Authorization"] = f"Bearer {auth_data.access_token}"
                    logger.info(f"Resolved auth headers for MCP server: {server_config.name}")
                else:
                    logger.warning(f"Token expired for MCP server: {server_config.name}")
            else:
                logger.warning(f"No valid auth token found for MCP server: {server_config.name}")

        except Exception as e:
            logger.error(f"Failed to resolve auth for MCP server {server_config.name}: {e}")

    return headers


async def create_mcp_session_with_retry(
    server_config: McpServerConfig,
    connection_stack: AsyncExitStack,
    user_id: str = "default",
    max_retries: int = 3
) -> ClientSession:
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
            session = await create_mcp_session(server_config, connection_stack, user_id)

            # If we succeed after retries, log it
            if attempt > 0:
                logger.info(
                    f"Successfully connected to MCP server '{server_config.name}' "
                    f"after {attempt + 1} attempt(s)"
                )

            return session

        except (ConnectionError, TimeoutError, OSError) as e:
            last_error = e

            # Don't retry on the last attempt
            if attempt < max_retries - 1:
                backoff_seconds = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    f"MCP connection attempt {attempt + 1}/{max_retries} failed for '{server_config.name}': {e}. "
                    f"Retrying in {backoff_seconds}s..."
                )
                await asyncio.sleep(backoff_seconds)
            else:
                # Final attempt failed
                logger.error(
                    f"Failed to connect to MCP server '{server_config.name}' "
                    f"after {max_retries} attempts"
                )

        except Exception as e:
            # Non-retryable errors (configuration issues, protocol errors, etc.)
            logger.error(
                f"Non-retryable error connecting to MCP server '{server_config.name}': {e}"
            )
            raise

    # All retries exhausted
    raise ConnectionError(
        f"Failed to connect to MCP server '{server_config.name}' after {max_retries} attempts. "
        f"Last error: {last_error}"
    ) from last_error


async def create_mcp_session(server_config: McpServerConfig, connection_stack: AsyncExitStack, user_id: str = "default") -> ClientSession:
    """Create MCP session using SDK transport factories."""
    transport_type = server_config.transport
    
    if transport_type == "stdio":
        from mcp.client.stdio import stdio_client
        
        server_params = StdioServerParameters(
            command=server_config.command,
            args=server_config.args,
            env=server_config.env or {}
        )
        
        read, write = await connection_stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await connection_stack.enter_async_context(
            ClientSession(read, write)
        )

        await initialize_mcp_session(session, server_config.name)
        return session
        
    elif transport_type == "http":
        # Resolve auth headers for HTTP transport
        resolved_headers = resolve_server_auth_headers(server_config, user_id)

        # Try streamable HTTP first (preferred), fall back to SSE
        try:
            from mcp.client.streamable_http import streamablehttp_client

            # Use streamable HTTP transport
            read, write, _ = await connection_stack.enter_async_context(
                streamablehttp_client(
                    url=server_config.url,
                    headers=resolved_headers,
                    timeout=server_config.timeout or 30.0
                )
            )
            session = await connection_stack.enter_async_context(
                ClientSession(read, write)
            )

            await initialize_mcp_session(session, server_config.name)
            return session
            
        except ImportError:
            raise NotImplementedError(
                "HTTP transport is not available. "
                "Please install the MCP SDK with HTTP support"
            )
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
            if any(keyword in arg.lower() for keyword in ['token', 'key', 'secret', 'password', 'auth']):
                safe_args.append('[REDACTED]')
            else:
                safe_args.append(arg)
        return f"stdio:{server_config.command} {' '.join(safe_args)}"
    elif server_config.transport == "http":
        # Sanitize URL for logging
        url = server_config.url or ""
        if '?' in url:
            url = url.split('?')[0]
        return f"http:{url}"
    else:
        return f"{server_config.transport}:unknown"


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
        input_schema: Dict[str, Any],
        output_schema: Dict[str, Any] | None,
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

    async def invoke(self, user_id: str, **kwargs) -> str:
        """
        Invoke the MCP tool with stateless connection.

        Creates a temporary connection, executes the tool, and closes the connection.
        This follows the "connect_and_execute" pattern.
        """
        try:
            # Validate inputs against schema
            if self.input_schema:
                self._validate_inputs(kwargs)

            # Stateless execution: connect → execute → close
            async with AsyncExitStack() as stack:
                # Create temporary connection
                session = await create_mcp_session(
                    self.server_config,
                    stack,
                    user_id
                )

                logger.debug(f"Executing MCP tool: {self.server_name}.{self.tool_name}")

                # Execute tool
                result = await session.call_tool(self.tool_name, kwargs)

                # Parse result
                parsed_result = self._parse_result(result)

                logger.debug(f"MCP tool {self.tool_name} completed successfully")

                # Connection auto-closes when exiting context
                return parsed_result

        except Exception as e:
            logger.error(f"Error invoking MCP tool {self.tool_name}: {e}")

            # Provide helpful error messages
            error_msg = str(e).lower()
            if 'timeout' in error_msg:
                raise RuntimeError(f"MCP tool '{self.tool_name}' timed out. Check server responsiveness.") from e
            elif 'connection' in error_msg:
                raise RuntimeError(f"MCP tool '{self.tool_name}' connection failed. Check server availability.") from e
            else:
                raise RuntimeError(f"MCP tool '{self.tool_name}' failed: {e}") from e

    def _parse_result(self, result: Any) -> str:
        """Parse MCP result into string format."""
        if hasattr(result, 'content'):
            if isinstance(result.content, list) and len(result.content) > 0:
                return str(result.content[0].text) if hasattr(result.content[0], 'text') else str(result.content[0])
            return str(result.content)
        elif hasattr(result, 'text'):
            return result.text
        else:
            return str(result)

    def _validate_inputs(self, kwargs: Dict[str, Any]) -> None:
        """Basic input validation against the tool's JSON schema."""
        if not isinstance(self.input_schema, dict):
            return

        properties = self.input_schema.get('properties', {})
        required = self.input_schema.get('required', [])

        # Check required parameters
        for req_param in required:
            if req_param not in kwargs:
                raise ValueError(f"Missing required parameter '{req_param}' for tool '{self.tool_name}'")

        # Warn about unexpected parameters
        for param in kwargs:
            if param not in properties:
                logger.warning(f"Unexpected parameter '{param}' for tool '{self.tool_name}'")


class McpPlugin(BasePlugin):
    """
    Plugin wrapper that holds stateless MCP tools for Semantic Kernel integration.

    This plugin creates kernel functions with proper type annotations from MCP JSON schemas,
    allowing Semantic Kernel to expose full parameter information to the LLM.

    MCP-Specific Design Note:
    -------------------------
    Unlike standard plugins, MCP plugins require a user_id parameter. This is necessary because:

    1. **Per-User Authentication**: MCP tools connect to external services that require OAuth2
       authentication. Tokens are stored per-user in AuthStorage and must be resolved at
       invocation time.

    2. **Dynamic Token Resolution**: Each MCP tool invocation calls resolve_server_auth_headers()
       which uses user_id to retrieve the current user's OAuth2 token from AuthStorage.

    3. **Multi-User Support**: The same MCP plugin class can be instantiated multiple times
       (once per user request), each with a different user_id for proper token isolation.

    This differs from standard plugins which typically use static authorization headers
    or no authentication at all.

    Args:
        tools: List of stateless MCP tools discovered from the server
        server_name: Name of the MCP server (used for logging and namespacing)
        user_id: User ID for OAuth2 token resolution (REQUIRED for MCP)
        authorization: Optional standard authorization header (rarely used with MCP)
        extra_data_collector: Optional collector for extra response data

    Raises:
        ValueError: If user_id is not provided (MCP requirement)

    Example:
        >>> # Discovery creates plugin class at session start
        >>> plugin_class = McpPluginRegistry.get_plugin_class("github")
        >>>
        >>> # Instantiation happens per-request with user_id
        >>> plugin_instance = plugin_class(
        ...     user_id="user123",
        ...     authorization="Bearer ...",
        ...     extra_data_collector=collector
        ... )
        >>> kernel.add_plugin(plugin_instance, "mcp_github")
    """

    def __init__(
        self,
        tools: List[McpTool],
        server_name: str,
        user_id: str,
        authorization: str | None = None,
        extra_data_collector=None
    ):
        if not user_id:
            raise ValueError(
                "MCP plugins require a user_id for per-request OAuth2 token resolution. "
                "This is needed to retrieve user-specific tokens from AuthStorage."
            )

        super().__init__(authorization, extra_data_collector)
        self.tools = tools
        self.server_name = server_name
        self.user_id = user_id

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

            # Build type annotations from JSON schema
            param_annotations = self._build_annotations(captured_tool.input_schema)

            @kernel_function(
                name=function_name,
                description=f"[{self.server_name}] {captured_tool.description}",
            )
            async def tool_function(**kwargs):
                return await captured_tool.invoke(self.user_id, **kwargs)

            # Add type annotations for SK introspection
            tool_function.__annotations__ = param_annotations

            return tool_function

        # Create the function and set as attribute
        tool_function = create_tool_function(tool)

        # Sanitize tool name for Python attribute
        attr_name = self._sanitize_name(f"{self.server_name}_{tool.tool_name}")

        setattr(self, attr_name, tool_function)

    def _build_annotations(self, input_schema: Dict[str, Any]) -> Dict[str, type]:
        """
        Convert MCP JSON schema to Python type annotations.

        This allows Semantic Kernel to introspect the function signature
        and expose full parameter information to the LLM.

        Args:
            input_schema: MCP tool's JSON schema for inputs

        Returns:
            Dictionary mapping parameter names to Python types
        """
        annotations = {}

        if not input_schema or not isinstance(input_schema, dict):
            annotations['return'] = str
            return annotations

        properties = input_schema.get('properties', {})
        required = input_schema.get('required', [])

        for param_name, param_schema in properties.items():
            if not isinstance(param_schema, dict):
                continue

            # Get Python type from JSON schema type
            param_type = self._json_type_to_python(param_schema.get('type', 'string'))

            # Mark as optional if not required
            # Note: SK will handle optional parameters appropriately
            annotations[param_name] = param_type

        # All MCP tools return strings currently
        annotations['return'] = str

        return annotations

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
            'string': str,
            'number': float,
            'integer': int,
            'boolean': bool,
            'array': list,
            'object': dict
        }
        return type_map.get(json_type, str)

    @staticmethod
    def _sanitize_name(name: str) -> str:
        """Sanitize name for Python attribute."""
        sanitized = ''.join(c if c.isalnum() or c == '_' else '_' for c in name)
        if not sanitized[0].isalpha() and sanitized[0] != '_':
            sanitized = f'tool_{sanitized}'
        return sanitized
