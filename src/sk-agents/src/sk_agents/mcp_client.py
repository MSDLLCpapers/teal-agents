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
from typing import Any, Dict, List, Optional
from contextlib import AsyncExitStack
from abc import ABC, abstractmethod

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


def get_package_version() -> str:
    """Get package version for MCP client identification."""
    try:
        from importlib.metadata import version
        return version('sk-agents')
    except Exception:
        return '1.0.0'  # Fallback version


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


def apply_trust_level_governance(base_governance: Governance, trust_level: str) -> Governance:
    """
    Apply server trust level controls to governance settings.

    Args:
        base_governance: Base governance settings
        trust_level: Server trust level ("trusted", "sandboxed", "untrusted")

    Returns:
        Governance: Governance with trust level controls applied
    """
    if trust_level == "untrusted":
        # Force HITL for all tools from untrusted servers
        return Governance(
            requires_hitl=True,
            cost="high",
            data_sensitivity="sensitive"
        )
    elif trust_level == "sandboxed":
        # Require HITL unless explicitly marked as safe
        return Governance(
            requires_hitl=True if base_governance.requires_hitl else True,  # Force HITL unless overridden
            cost=base_governance.cost if base_governance.cost != "low" else "medium",  # Elevate cost
            data_sensitivity=base_governance.data_sensitivity
        )
    else:  # trusted
        # Use base governance as-is for trusted servers
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
        headers.update(server_config.headers)

    # If server has auth configuration, resolve tokens using existing auth system
    if server_config.auth_server and server_config.scopes:
        try:
            # Use AuthStorageFactory directly - no wrapper needed
            from ska_utils import AppConfig
            app_config = AppConfig()
            auth_storage_factory = AuthStorageFactory(app_config)
            auth_storage = auth_storage_factory.get_auth_storage_manager()

            # Generate composite key for OAuth2 token lookup
            composite_key = f"{server_config.auth_server}|{sorted(server_config.scopes)}"

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


def json_schema_to_python_params(input_schema: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert MCP JSON Schema to Python function parameter information.

    Args:
        input_schema: JSON Schema from MCP tool definition

    Returns:
        Dict containing parameter info for dynamic function generation
    """
    if not isinstance(input_schema, dict):
        return {}

    properties = input_schema.get('properties', {})
    required = set(input_schema.get('required', []))
    params = {}

    # Map JSON Schema types to Python types
    type_mapping = {
        'string': str,
        'number': float,
        'integer': int,
        'boolean': bool,
        'array': list,
        'object': dict
    }

    for param_name, param_def in properties.items():
        param_type = type_mapping.get(param_def.get('type', 'string'), str)
        is_required = param_name in required
        default_value = param_def.get('default', None if is_required else "")

        params[param_name] = {
            'type': param_type,
            'required': is_required,
            'default': default_value,
            'description': param_def.get('description', '')
        }

    return params


def create_mcp_function_signature(tool: 'McpTool'):
    """
    Create a properly typed function signature for an MCP tool.

    Args:
        tool: McpTool instance with JSON schema

    Returns:
        Function with proper signature that calls tool.invoke()
    """
    import inspect
    from typing import get_type_hints

    # Get parameter information from JSON schema
    params_info = json_schema_to_python_params(tool.input_schema)

    # Build function signature dynamically
    sig_params = []

    # Always include 'self' as first parameter since this will be a method
    sig_params.append(inspect.Parameter('self', inspect.Parameter.POSITIONAL_OR_KEYWORD))

    # Add parameters from schema
    for param_name, param_info in params_info.items():
        param_type = param_info['type']
        is_required = param_info['required']
        default_value = param_info['default']

        if is_required:
            param = inspect.Parameter(
                param_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=param_type
            )
        else:
            param = inspect.Parameter(
                param_name,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
                annotation=param_type,
                default=default_value
            )
        sig_params.append(param)

    # Create the function signature
    signature = inspect.Signature(sig_params)

    # Create the actual function
    async def mcp_function(self, **kwargs):
        # Filter kwargs to only include parameters defined in schema
        filtered_kwargs = {}
        for param_name in params_info.keys():
            if param_name in kwargs:
                filtered_kwargs[param_name] = kwargs[param_name]

        return await tool.invoke(**filtered_kwargs)

    # Apply the signature to the function
    mcp_function.__signature__ = signature
    mcp_function.__name__ = f"mcp_{tool.name}"

    return mcp_function


class McpTool:
    """Wrapper for MCP tools with just-in-time connection execution."""

    def __init__(self, name: str, description: str, input_schema: Dict[str, Any], server_config: McpServerConfig, mcp_client: 'McpClient', user_id: str = "default"):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.server_config = server_config
        self.server_name = server_config.name
        self.mcp_client = mcp_client
        self.user_id = user_id
        self.original_name = name

    async def invoke(self, **kwargs) -> str:
        """
        Invoke the MCP tool using just-in-time connection.

        Note: Parameter validation is handled by Semantic Kernel
        via the properly typed function signatures.
        """
        try:
            # Use McpClient's connect_and_execute_tool for just-in-time execution
            result_text = await self.mcp_client.connect_and_execute_tool(
                self.server_name,
                self.name,
                kwargs,
                self.user_id
            )

            return result_text

        except Exception as e:
            logger.error(f"Error invoking MCP tool {self.name}: {e}")

            # Provide helpful error messages
            error_msg = str(e).lower()
            if 'timeout' in error_msg:
                raise RuntimeError(f"MCP tool '{self.name}' timed out. Check server responsiveness.") from e
            elif 'connection' in error_msg:
                raise RuntimeError(f"MCP tool '{self.name}' connection failed. Check server availability.") from e
            else:
                raise RuntimeError(f"MCP tool '{self.name}' failed: {e}") from e


class McpPlugin(BasePlugin):
    """Plugin wrapper that holds MCP tools for Semantic Kernel integration."""
    
    def __init__(self, tools: List[McpTool], server_name: str = None, authorization: str | None = None, extra_data_collector=None):
        super().__init__(authorization, extra_data_collector)
        self.tools = tools
        self.server_name = server_name
        
        # Dynamically add kernel functions for each tool
        for tool in tools:
            self._add_tool_function(tool)
    
    def _add_tool_function(self, tool: McpTool):
        """Add a tool as a kernel function to this plugin with proper signature."""

        # Create unique tool name to avoid collisions
        unique_name = f"{self.server_name}_{tool.name}" if self.server_name else tool.name

        # Generate function with proper signature from JSON schema
        tool_function = create_mcp_function_signature(tool)

        # Apply kernel function decorator
        decorated_function = kernel_function(
            name=unique_name,
            description=f"[{self.server_name or 'MCP'}] {tool.description}",
        )(tool_function)

        # Sanitize tool name for Python attribute
        base_name = f"{self.server_name}_{tool.name}" if self.server_name else tool.name
        attr_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in base_name)
        if not attr_name[0].isalpha() and attr_name[0] != '_':
            attr_name = f'tool_{attr_name}'

        setattr(self, attr_name, decorated_function)


class McpClient:
    """
    Multi-server MCP client manager with ephemeral connections.

    This class manages ephemeral connections to MCP servers for tool discovery
    and execution. Connections are created just-in-time for tool invocation
    and closed immediately after use.

    Currently supported:
    - stdio: Local subprocess communication
    - http: HTTP with Server-Sent Events for remote servers

    Future transports will be added as they become available in the MCP SDK.
    """

    def __init__(self):
        """Initialize the MCP client."""
        self.server_configs: Dict[str, McpServerConfig] = {}
        self.plugins: Dict[str, McpPlugin] = {}
        
    async def discover_and_register_tools(self, server_config: McpServerConfig, user_id: str | None = None, session_id: str = "default") -> None:
        """
        Discover tools from an MCP server and register them (using ephemeral connection).

        Args:
            server_config: Configuration for the MCP server
            user_id: Optional user ID for authentication
            session_id: Session ID for tool registration

        Raises:
            ConnectionError: If connection to the MCP server fails
            ValueError: If server configuration is invalid
        """
        # Validate governance configuration for production security
        self._validate_governance_configuration(server_config)
        connection_stack = AsyncExitStack()
        try:
            # Get transport info for logging
            transport_info = get_transport_info(server_config)
            logger.info(f"Discovering tools from MCP server '{server_config.name}' via {transport_info}")

            # Create temporary session for tool discovery
            session = await create_mcp_session(server_config, connection_stack, user_id or "default")

            # Initialize the session with proper protocol negotiation
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
                f"MCP session initialized for '{server_config.name}': "
                f"server={getattr(init_result, 'server_info', 'unknown')}, "
                f"protocol={getattr(init_result, 'protocol_version', 'unknown')}"
            )

            # Apply smart defaults based on server capabilities
            self._apply_smart_defaults(server_config, session)

            # Store server config for later use in tool execution
            self.server_configs[server_config.name] = server_config

            # Discover and register tools
            await self._discover_and_register_tools(server_config.name, session, session_id, user_id or "default")

            logger.info(f"Successfully discovered tools from MCP server: {server_config.name}")

        except Exception as e:
            logger.error(f"Failed to discover tools from MCP server '{server_config.name}': {e}")

            # Provide transport-specific error guidance
            error_msg = str(e).lower()

            # Enhanced protocol error detection
            if 'protocol' in error_msg and ('version' in error_msg or 'unsupported' in error_msg):
                raise ConnectionError(
                    f"Protocol version mismatch with server '{server_config.name}'. "
                    f"Client supports '2025-03-26'. Server error: {e}"
                ) from e

            if server_config.transport == "stdio":
                # Stdio-specific errors
                if 'permission' in error_msg or 'access' in error_msg:
                    raise ConnectionError(
                        f"Permission denied for MCP server '{server_config.name}'. "
                        f"Check executable permissions for: {server_config.command}"
                    ) from e
                elif 'not found' in error_msg or 'no such file' in error_msg:
                    raise ConnectionError(
                        f"Command not found for MCP server '{server_config.name}'. "
                        f"Verify command is in PATH or use absolute path: {server_config.command}"
                    ) from e
            elif server_config.transport == "http":
                # HTTP-specific errors
                if 'timeout' in error_msg or 'timed out' in error_msg:
                    raise ConnectionError(
                        f"Timeout connecting to MCP server '{server_config.name}' at {server_config.url}. "
                        f"Check server availability and network connectivity."
                    ) from e
                elif 'connection' in error_msg or 'unreachable' in error_msg:
                    raise ConnectionError(
                        f"Cannot reach MCP server '{server_config.name}' at {server_config.url}. "
                        f"Verify the URL is correct and the server is running."
                    ) from e
                elif '401' in error_msg or 'unauthorized' in error_msg:
                    raise ConnectionError(
                        f"Authentication failed for MCP server '{server_config.name}'. "
                        f"Check your credentials and authorization headers."
                    ) from e
                elif '404' in error_msg or 'not found' in error_msg:
                    raise ConnectionError(
                        f"MCP server endpoint not found: {server_config.url}. "
                        f"Verify the URL path is correct (typically ends with /sse or /mcp)."
                    ) from e
                elif '503' in error_msg or 'unavailable' in error_msg:
                    raise ConnectionError(
                        f"MCP server '{server_config.name}' is temporarily unavailable. "
                        f"Try again later or contact the server administrator."
                    ) from e

            # Generic fallback error
            raise ConnectionError(f"Could not connect to MCP server '{server_config.name}': {e}") from e

        finally:
            # Always close the ephemeral connection
            await connection_stack.aclose()
            logger.debug(f"Closed ephemeral connection to MCP server: {server_config.name}")

    async def connect_and_execute_tool(self, server_name: str, tool_name: str, arguments: Dict[str, Any], user_id: str = "default") -> str:
        """
        Connect to MCP server, execute a specific tool, and disconnect.

        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to execute
            arguments: Arguments to pass to the tool
            user_id: User ID for authentication

        Returns:
            str: Tool execution result

        Raises:
            ConnectionError: If connection fails
            ValueError: If server or tool not found
        """
        if server_name not in self.server_configs:
            raise ValueError(f"MCP server '{server_name}' not configured")

        server_config = self.server_configs[server_name]
        connection_stack = AsyncExitStack()

        try:
            logger.debug(f"Creating ephemeral connection to execute tool '{tool_name}' on server '{server_name}'")

            # Create temporary session for tool execution
            session = await create_mcp_session(server_config, connection_stack, user_id)
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
            logger.debug(
                f"MCP session initialized for tool execution on '{server_name}': "
                f"server={getattr(init_result, 'server_info', 'unknown')}, "
                f"protocol={getattr(init_result, 'protocol_version', 'unknown')}"
            )

            # Execute the tool with timeout
            try:
                result = await asyncio.wait_for(
                    session.call_tool(tool_name, arguments),
                    timeout=server_config.request_timeout or 30.0
                )
            except asyncio.TimeoutError:
                raise ConnectionError(
                    f"Tool '{tool_name}' execution timed out on server '{server_name}' after {server_config.request_timeout or 30.0}s"
                )

            logger.debug(f"Successfully executed tool '{tool_name}' on server '{server_name}'")
            return str(result.content[0].text) if result.content else "No content returned"

        except Exception as e:
            logger.error(f"Failed to execute tool '{tool_name}' on server '{server_name}': {e}")

            # Enhanced protocol error detection
            error_msg = str(e).lower()
            if 'protocol' in error_msg and ('version' in error_msg or 'unsupported' in error_msg):
                raise ConnectionError(
                    f"Protocol version mismatch with server '{server_name}'. "
                    f"Client supports '2025-03-26'. Server error: {e}"
                ) from e

            raise ConnectionError(f"Tool execution failed: {e}") from e

        finally:
            # Always close the ephemeral connection
            await connection_stack.aclose()
            logger.debug(f"Closed ephemeral connection after executing tool '{tool_name}'")

    def _apply_smart_defaults(self, server_config: McpServerConfig, session) -> None:
        """
        Apply intelligent defaults based on MCP server capabilities.

        Args:
            server_config: MCP server configuration to adjust
            session: Initialized MCP session
        """
        try:
            # For HTTP transport, adjust timeouts based on server characteristics
            if server_config.transport == "http":
                # Get server info if available (this might not be accessible from session)
                # For now, we'll use simple heuristics

                # Base timeout adjustments
                if server_config.timeout is None:
                    # Set longer timeout for initial connections
                    server_config.timeout = 45.0
                    logger.debug(f"Set default timeout to {server_config.timeout}s for {server_config.name}")

                if server_config.sse_read_timeout is None:
                    # Set longer SSE timeout for servers that might have many tools
                    server_config.sse_read_timeout = 600.0
                    logger.debug(f"Set default SSE timeout to {server_config.sse_read_timeout}s for {server_config.name}")

                # Log the applied defaults
                logger.info(
                    f"Applied smart defaults for MCP server '{server_config.name}': "
                    f"timeout={server_config.timeout}s, sse_read_timeout={server_config.sse_read_timeout}s"
                )

        except Exception as e:
            logger.warning(f"Failed to apply smart defaults for {server_config.name}: {e}")

    async def _discover_and_register_tools(self, server_name: str, session, session_id: str = "default", user_id: str = "default") -> None:
        """Discover tools from MCP server and register them directly in existing catalog."""
        try:
            server_config = self.server_configs[server_name]

            # List available tools from the server with timeout
            try:
                tools_result = await asyncio.wait_for(
                    session.list_tools(),
                    timeout=server_config.request_timeout or 30.0
                )
            except asyncio.TimeoutError:
                raise ConnectionError(
                    f"Tool discovery timed out for server '{server_name}' after {server_config.request_timeout or 30.0}s. "
                    f"Server may be unresponsive."
                )

            if not tools_result or not hasattr(tools_result, 'tools'):
                logger.warning(f"No tools found on MCP server: {server_name}")
                return

            # Get the existing plugin catalog - no wrapper needed
            try:
                catalog = PluginCatalogFactory().get_catalog()
            except Exception as e:
                logger.warning(f"Could not get plugin catalog for MCP registration: {e}")
                catalog = None

            # Create plugin tools and register directly in catalog
            mcp_tools = []
            plugin_tools = []

            for tool_info in tools_result.tools:
                # Create MCP tool wrapper for Semantic Kernel with just-in-time execution
                mcp_tool = McpTool(
                    name=tool_info.name,
                    description=tool_info.description or f"Tool {tool_info.name} from {server_name}",
                    input_schema=getattr(tool_info, 'inputSchema', {}) or {},
                    server_config=server_config,
                    mcp_client=self,
                    user_id=user_id or "default"
                )
                mcp_tools.append(mcp_tool)

                # Create PluginTool for catalog registration (first-class citizen)
                if catalog:
                    # Create session-scoped tool_id that matches HITL expectations
                    tool_id = f"mcp_{session_id}_{server_name}-{server_name}_{tool_info.name}"

                    # Map MCP annotations to governance and apply trust level + overrides
                    annotations = getattr(tool_info, 'annotations', {}) or {}
                    tool_description = tool_info.description or f"Tool {tool_info.name} from {server_name}"
                    base_governance = map_mcp_annotations_to_governance(annotations, tool_description)

                    # Apply server trust level governance controls
                    trust_governance = apply_trust_level_governance(base_governance, server_config.trust_level)

                    # Apply tool-specific overrides (highest priority)
                    governance = apply_governance_overrides(trust_governance, tool_info.name, server_config.tool_governance_overrides)

                    # Create auth configuration if server has auth
                    auth = None
                    if server_config.auth_server and server_config.scopes:
                        auth = Oauth2PluginAuth(
                            auth_server=server_config.auth_server,
                            scopes=server_config.scopes
                        )

                    plugin_tool = PluginTool(
                        tool_id=tool_id,
                        name=getattr(tool_info, 'title', None) or tool_info.name,
                        description=tool_info.description or f"MCP tool: {tool_info.name}",
                        governance=governance,
                        auth=auth
                    )
                    plugin_tools.append(plugin_tool)

                logger.info(f"Discovered tool: {tool_info.name} from server {server_name}")

            # Register tools directly in existing catalog with session scope
            if catalog and plugin_tools:
                plugin_id = f"mcp-{session_id}-{server_name}"

                # Create the MCP plugin
                from sk_agents.plugin_catalog.models import McpPluginType, Plugin
                plugin = Plugin(
                    plugin_id=plugin_id,
                    name=f"MCP Server: {server_name}",
                    description=f"Tools from MCP server '{server_name}'",
                    version="1.0.0",
                    owner="mcp-integration",
                    plugin_type=McpPluginType(),
                    tools=plugin_tools
                )

                # Register directly in existing catalog - no wrapper
                catalog.register_dynamic_plugin(plugin)
                logger.info(f"Registered {len(plugin_tools)} MCP tools directly in existing catalog for server {server_name}")

            # Create semantic kernel plugin
            if mcp_tools:
                plugin = McpPlugin(mcp_tools, server_name=server_name)
                self.plugins[server_name] = plugin
                logger.info(f"Created Semantic Kernel plugin for server {server_name} with {len(mcp_tools)} tools")

                # Apply additional smart defaults based on tool count
                self._adjust_defaults_for_tool_count(server_name, len(mcp_tools))

        except Exception as e:
            logger.error(f"Failed to discover tools from MCP server {server_name}: {e}")
            raise

    def _adjust_defaults_for_tool_count(self, server_name: str, tool_count: int) -> None:
        """
        Adjust server configuration defaults based on the number of discovered tools.

        Args:
            server_name: Name of the MCP server
            tool_count: Number of tools discovered
        """
        server_config = self.server_configs.get(server_name)
        if not server_config or server_config.transport != "http":
            return

        try:
            # Adjust timeouts based on tool count
            original_timeout = server_config.timeout
            original_sse_timeout = server_config.sse_read_timeout

            # More tools = potentially longer operations, increase timeouts
            if tool_count > 10:
                # Large server with many tools
                server_config.timeout = max(server_config.timeout or 30.0, 60.0)
                server_config.sse_read_timeout = max(server_config.sse_read_timeout or 300.0, 900.0)
            elif tool_count > 5:
                # Medium server
                server_config.timeout = max(server_config.timeout or 30.0, 45.0)
                server_config.sse_read_timeout = max(server_config.sse_read_timeout or 300.0, 600.0)
            else:
                # Small server, keep default timeouts
                pass

            # Log changes if timeouts were adjusted
            if (server_config.timeout != original_timeout or
                server_config.sse_read_timeout != original_sse_timeout):
                logger.info(
                    f"Adjusted timeouts for {server_name} ({tool_count} tools): "
                    f"timeout={server_config.timeout}s, sse_read_timeout={server_config.sse_read_timeout}s"
                )

        except Exception as e:
            logger.warning(f"Failed to adjust defaults for {server_name}: {e}")

    def get_plugin(self, server_name: str) -> Optional[McpPlugin]:
        """Get the plugin for a specific MCP server."""
        return self.plugins.get(server_name)
    
    def get_all_plugins(self) -> Dict[str, McpPlugin]:
        """Get all registered MCP plugins."""
        return self.plugins.copy()
    
    def register_plugins_with_kernel(self, kernel: Kernel) -> None:
        """Register all MCP plugins with a Semantic Kernel instance."""
        for server_name, plugin in self.plugins.items():
            try:
                kernel.add_plugin(plugin, f"mcp_{server_name}")
                logger.info(f"Registered MCP plugin for server {server_name} with kernel")
            except Exception as e:
                logger.error(f"Failed to register MCP plugin for server {server_name}: {e}")
                raise
    
    def cleanup_session_plugins(self, session_id: str) -> None:
        """Clean up session-scoped catalog registrations for all servers."""
        try:
            catalog = PluginCatalogFactory().get_catalog()
            for server_name in self.server_configs.keys():
                plugin_id = f"mcp-{session_id}-{server_name}"
                if catalog.unregister_dynamic_plugin(plugin_id):
                    logger.info(f"Unregistered session-scoped MCP plugin '{plugin_id}' from catalog")
        except Exception as e:
            logger.warning(f"Could not clean up session plugins for session {session_id}: {e}")

    def get_configured_servers(self) -> List[str]:
        """Get list of configured MCP server names."""
        return list(self.server_configs.keys())

    def _validate_governance_configuration(self, server_config: McpServerConfig) -> None:
        """
        Validate governance configuration for security best practices.

        Args:
            server_config: MCP server configuration to validate

        Raises:
            ValueError: If configuration violates security requirements
        """
        # Check for production security requirements
        if server_config.trust_level == "untrusted":
            if not server_config.tool_governance_overrides:
                logger.warning(
                    f"MCP server '{server_config.name}' is marked as 'untrusted' but has no "
                    f"governance overrides. All tools will require HITL approval by default."
                )

        elif server_config.trust_level == "trusted":
            if not server_config.tool_governance_overrides:
                logger.warning(
                    f"MCP server '{server_config.name}' is marked as 'trusted' but has no "
                    f"governance overrides. Consider reviewing all tools for security risks."
                )

            # Recommend explicit governance for trusted servers
            logger.info(
                f"Server '{server_config.name}' is trusted. Ensure all tools have been "
                f"security reviewed and appropriate governance overrides are configured."
            )

        # Validate authentication for remote servers
        if server_config.transport == "http":
            if not server_config.auth_server and not server_config.headers:
                logger.warning(
                    f"Remote MCP server '{server_config.name}' has no authentication configured. "
                    f"This may pose security risks."
                )

        # Log governance policy for audit trail
        logger.info(
            f"MCP server '{server_config.name}' configuration validated: "
            f"trust_level={server_config.trust_level}, "
            f"has_overrides={bool(server_config.tool_governance_overrides)}, "
            f"has_auth={bool(server_config.auth_server or server_config.headers)}"
        )


