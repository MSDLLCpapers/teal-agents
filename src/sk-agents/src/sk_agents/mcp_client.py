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
import threading
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


def map_mcp_annotations_to_governance(annotations: Dict[str, Any]) -> Governance:
    """
    Map MCP tool annotations to Teal Agents governance policies.

    Args:
        annotations: MCP tool annotations

    Returns:
        Governance: Governance settings for the tool
    """
    # Map MCP destructiveHint to HITL requirement
    destructive_hint = annotations.get("destructiveHint", False)
    requires_hitl = destructive_hint

    # Map destructive operations to higher cost and sensitivity
    if destructive_hint:
        cost = "high"
        data_sensitivity = "sensitive"
    else:
        # Check if it's read-only
        read_only_hint = annotations.get("readOnlyHint", False)
        if read_only_hint:
            cost = "low"
            data_sensitivity = "public"
        else:
            cost = "medium"
            data_sensitivity = "proprietary"

    return Governance(
        requires_hitl=requires_hitl,
        cost=cost,
        data_sensitivity=data_sensitivity
    )


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
            # Fall back to SSE transport if streamable HTTP not available
            try:
                from mcp.client.sse import sse_client
                
                read, write = await connection_stack.enter_async_context(
                    sse_client(
                        url=server_config.url,
                        headers=resolved_headers,
                        timeout=server_config.timeout or 30.0,
                        sse_read_timeout=server_config.sse_read_timeout or 300.0
                    )
                )
                session = await connection_stack.enter_async_context(
                    ClientSession(read, write)
                )
                
                return session
                
            except ImportError:
                raise NotImplementedError(
                    "HTTP transport is not available. "
                    "Please install the MCP SDK with HTTP support: "
                    "pip install 'mcp[http]' or 'mcp[sse]'"
                )
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
    """Wrapper for MCP tools to make them compatible with Semantic Kernel."""

    def __init__(self, name: str, description: str, input_schema: Dict[str, Any], client_session, server_name: str = None):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.client_session = client_session
        self.server_name = server_name
        self.original_name = name
        
    async def invoke(self, **kwargs) -> str:
        """Invoke the MCP tool with the provided arguments."""
        try:
            # Basic input validation if schema is available
            if self.input_schema:
                self._validate_inputs(kwargs)
                
            result = await self.client_session.call_tool(self.name, kwargs)
            
            # Handle different result types from MCP
            if hasattr(result, 'content'):
                if isinstance(result.content, list) and len(result.content) > 0:
                    return str(result.content[0].text) if hasattr(result.content[0], 'text') else str(result.content[0])
                return str(result.content)
            elif hasattr(result, 'text'):
                return result.text
            else:
                return str(result)
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
            
    def _validate_inputs(self, kwargs: Dict[str, Any]) -> None:
        """Basic input validation against the tool's JSON schema."""
        if not isinstance(self.input_schema, dict):
            return
            
        properties = self.input_schema.get('properties', {})
        required = self.input_schema.get('required', [])
        
        # Check required parameters
        for req_param in required:
            if req_param not in kwargs:
                raise ValueError(f"Missing required parameter '{req_param}' for tool '{self.name}'")
        
        # Warn about unexpected parameters
        for param in kwargs:
            if param not in properties:
                logger.warning(f"Unexpected parameter '{param}' for tool '{self.name}'")


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
        """Add a tool as a kernel function to this plugin."""
        
        # Create a closure that captures the specific tool instance
        def create_tool_function(captured_tool: McpTool):
            # Create unique tool name to avoid collisions
            unique_name = f"{self.server_name}_{captured_tool.name}" if self.server_name else captured_tool.name
            
            @kernel_function(
                name=unique_name,
                description=f"[{self.server_name or 'MCP'}] {captured_tool.description}",
            )
            async def tool_function(**kwargs):
                return await captured_tool.invoke(**kwargs)
            return tool_function
        
        # Create the function and set as attribute
        tool_function = create_tool_function(tool)
        
        # Sanitize tool name for Python attribute
        base_name = f"{self.server_name}_{tool.name}" if self.server_name else tool.name
        attr_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in base_name)
        if not attr_name[0].isalpha() and attr_name[0] != '_':
            attr_name = f'tool_{attr_name}'
            
        setattr(self, attr_name, tool_function)


class McpClient:
    """
    Multi-server MCP client manager with Semantic Kernel integration.
    
    This class manages connections to multiple MCP servers and provides
    seamless integration with the Semantic Kernel framework. It uses the
    MCP Python SDK for actual transport handling.
    
    Currently supported:
    - stdio: Local subprocess communication
    
    Future transports will be added as they become available in the MCP SDK.
    """
    
    def __init__(self):
        """Initialize the MCP client."""
        self.connected_servers: Dict[str, Any] = {}
        self.server_configs: Dict[str, McpServerConfig] = {}
        self.plugins: Dict[str, McpPlugin] = {}
        self._connection_stacks: Dict[str, AsyncExitStack] = {}
        self._connection_health: Dict[str, bool] = {}
        
    async def connect_server(self, server_config: McpServerConfig, user_id: str | None = None, session_id: str = "default") -> None:
        """
        Connect to an MCP server and register its tools.
        
        Args:
            server_config: Configuration for the MCP server to connect to
            
        Raises:
            ConnectionError: If connection to the MCP server fails
            ValueError: If server configuration is invalid
        """
        # Clean up any existing connection first
        await self.disconnect_server(server_config.name)
        
        connection_stack = AsyncExitStack()
        try:
            # Get transport info for logging
            transport_info = get_transport_info(server_config)
            logger.info(f"Connecting to MCP server '{server_config.name}' via {transport_info}")
            
            # Create session using MCP SDK
            session = await create_mcp_session(server_config, connection_stack)
            
            # Initialize the session
            await session.initialize()

            # Apply smart defaults based on server capabilities
            self._apply_smart_defaults(server_config, session)

            # Store the session and resources
            self.connected_servers[server_config.name] = session
            self.server_configs[server_config.name] = server_config
            self._connection_stacks[server_config.name] = connection_stack
            self._connection_health[server_config.name] = True
            
            # Discover and register tools with session context
            await self._discover_and_register_tools(server_config.name, session, session_id)
            
            logger.info(f"Successfully connected to MCP server: {server_config.name}")
            
        except Exception as e:
            # Cleanup on failure
            await connection_stack.aclose()
            logger.error(f"Failed to connect to MCP server '{server_config.name}': {e}")
            
            # Provide transport-specific error guidance
            error_msg = str(e).lower()
            
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

    async def _discover_and_register_tools(self, server_name: str, session, session_id: str = "default") -> None:
        """Discover tools from MCP server and register them directly in existing catalog."""
        try:
            # List available tools from the server
            tools_result = await session.list_tools()

            if not tools_result or not hasattr(tools_result, 'tools'):
                logger.warning(f"No tools found on MCP server: {server_name}")
                return

            server_config = self.server_configs[server_name]

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
                # Create MCP tool wrapper for Semantic Kernel
                mcp_tool = McpTool(
                    name=tool_info.name,
                    description=tool_info.description or f"Tool {tool_info.name} from {server_name}",
                    input_schema=getattr(tool_info, 'inputSchema', {}) or {},
                    client_session=session,
                    server_name=server_name
                )
                mcp_tools.append(mcp_tool)

                # Create PluginTool for catalog registration (first-class citizen)
                if catalog:
                    # Create session-scoped tool_id that matches HITL expectations
                    tool_id = f"mcp_{session_id}_{server_name}-{server_name}_{tool_info.name}"

                    # Map MCP annotations to governance and apply any overrides
                    annotations = getattr(tool_info, 'annotations', {}) or {}
                    base_governance = map_mcp_annotations_to_governance(annotations)
                    governance = apply_governance_overrides(base_governance, tool_info.name, server_config.tool_governance_overrides)

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
    
    async def disconnect_server(self, server_name: str, session_id: str = "default") -> None:
        """Disconnect from an MCP server and clean up resources."""
        try:
            # Clean up session-scoped catalog registration
            try:
                catalog = PluginCatalogFactory().get_catalog()
                plugin_id = f"mcp-{session_id}-{server_name}"
                if catalog.unregister_dynamic_plugin(plugin_id):
                    logger.info(f"Unregistered session-scoped MCP plugin '{plugin_id}' from catalog")
            except Exception as e:
                logger.warning(f"Could not unregister MCP plugin from catalog: {e}")

            # Clean up connection resources
            if server_name in self._connection_stacks:
                connection_stack = self._connection_stacks[server_name]
                await connection_stack.aclose()
                del self._connection_stacks[server_name]

            # Clean up tracking dictionaries
            for dictionary in [
                self.connected_servers,
                self.server_configs,
                self.plugins,
                self._connection_health
            ]:
                if server_name in dictionary:
                    del dictionary[server_name]

            logger.info(f"Disconnected from MCP server: {server_name}")

        except Exception as e:
            logger.error(f"Error disconnecting from MCP server {server_name}: {e}")
    
    async def disconnect_all(self) -> None:
        """Disconnect from all connected MCP servers."""
        server_names = list(self.connected_servers.keys())
        disconnect_tasks = [self.disconnect_server(name) for name in server_names]
        if disconnect_tasks:
            await asyncio.gather(*disconnect_tasks, return_exceptions=True)
    
    def is_connected(self, server_name: str) -> bool:
        """Check if connected to a specific MCP server."""
        return (
            server_name in self.connected_servers and 
            server_name in self._connection_health and
            self._connection_health[server_name]
        )
        
    def mark_connection_unhealthy(self, server_name: str) -> None:
        """Mark a connection as unhealthy."""
        if server_name in self._connection_health:
            self._connection_health[server_name] = False
            logger.warning(f"Marked MCP server {server_name} as unhealthy")
    
    def get_connected_servers(self) -> List[str]:
        """Get list of connected MCP server names."""
        return list(self.connected_servers.keys())


class SessionMcpClientRegistry:
    """Session-scoped registry for MCP client instances."""

    _session_clients: Dict[str, McpClient] = {}
    _session_locks: Dict[str, asyncio.Lock] = {}
    _cleanup_tasks: Dict[str, asyncio.Task] = {}
    _registry_lock = threading.Lock()

    @classmethod
    async def get_or_create_client(cls, session_id: str) -> McpClient:
        """Get or create MCP client for specific session."""
        # Ensure session lock exists
        if session_id not in cls._session_locks:
            with cls._registry_lock:
                if session_id not in cls._session_locks:
                    cls._session_locks[session_id] = asyncio.Lock()

        # Get or create client for session
        async with cls._session_locks[session_id]:
            if session_id not in cls._session_clients:
                cls._session_clients[session_id] = McpClient()
                logger.info(f"Created new MCP client for session: {session_id}")

                # Schedule automatic cleanup
                cls._schedule_cleanup(session_id, delay_minutes=60)

            return cls._session_clients[session_id]

    @classmethod
    async def cleanup_session(cls, session_id: str) -> None:
        """Clean up MCP client and resources for a specific session."""
        try:
            # Cancel any scheduled cleanup
            if session_id in cls._cleanup_tasks:
                cleanup_task = cls._cleanup_tasks[session_id]
                if not cleanup_task.done():
                    cleanup_task.cancel()
                del cls._cleanup_tasks[session_id]

            # Clean up client if exists
            if session_id in cls._session_clients:
                client = cls._session_clients[session_id]
                await client.disconnect_all()
                del cls._session_clients[session_id]
                logger.info(f"Cleaned up MCP client for session: {session_id}")

            # Clean up session lock
            if session_id in cls._session_locks:
                del cls._session_locks[session_id]

        except Exception as e:
            logger.error(f"Error cleaning up session {session_id}: {e}")

    @classmethod
    def _schedule_cleanup(cls, session_id: str, delay_minutes: int = 60) -> None:
        """Schedule automatic cleanup for abandoned sessions."""
        async def cleanup_after_delay():
            await asyncio.sleep(delay_minutes * 60)
            logger.info(f"Auto-cleaning up abandoned session: {session_id}")
            await cls.cleanup_session(session_id)

        # Cancel existing cleanup task if any
        if session_id in cls._cleanup_tasks:
            existing_task = cls._cleanup_tasks[session_id]
            if not existing_task.done():
                existing_task.cancel()

        # Schedule new cleanup
        try:
            task = asyncio.create_task(cleanup_after_delay())
            cls._cleanup_tasks[session_id] = task
        except RuntimeError:
            # No event loop running, cleanup will happen when session explicitly ends
            logger.debug(f"No event loop for auto-cleanup of session {session_id}")

    @classmethod
    def get_active_sessions(cls) -> List[str]:
        """Get list of active session IDs."""
        return list(cls._session_clients.keys())


async def get_mcp_client_for_session(session_id: str) -> McpClient:
    """Get MCP client instance for specific session."""
    return await SessionMcpClientRegistry.get_or_create_client(session_id)


async def cleanup_mcp_session(session_id: str) -> None:
    """Clean up MCP resources for specific session."""
    await SessionMcpClientRegistry.cleanup_session(session_id)