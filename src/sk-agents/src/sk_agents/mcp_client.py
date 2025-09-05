"""
MCP Client for Teal Agents Platform.

This module provides an MCP (Model Context Protocol) client that can connect to MCP servers
and automatically register their tools with the Semantic Kernel framework.
"""

import asyncio
import logging
import threading
from typing import Any, Dict, List, Optional, Tuple
from contextlib import AsyncExitStack
from abc import ABC, abstractmethod

from mcp import ClientSession, StdioServerParameters
from semantic_kernel.functions import kernel_function
from semantic_kernel.kernel import Kernel

from sk_agents.ska_types import BasePlugin
from sk_agents.tealagents.v1alpha1.config import McpServerConfig


logger = logging.getLogger(__name__)


class McpTransport(ABC):
    """Abstract base class for MCP transport implementations."""
    
    @abstractmethod
    async def create_session(self, connection_stack: AsyncExitStack) -> ClientSession:
        """Create and return an MCP client session."""
        pass
        
    @abstractmethod
    def get_transport_info(self) -> str:
        """Return a string describing this transport for logging."""
        pass


class StdioTransport(McpTransport):
    """MCP transport using stdio/subprocess communication."""
    
    def __init__(self, server_config: 'McpServerConfig'):
        self.server_config = server_config
        
    async def create_session(self, connection_stack: AsyncExitStack) -> ClientSession:
        """Create stdio-based MCP session."""
        from mcp.client.stdio import stdio_client
        
        server_params = StdioServerParameters(
            command=self.server_config.command,
            args=self.server_config.args,
            env=self.server_config.env or {}
        )
        
        # Create persistent connection using AsyncExitStack
        read, write = await connection_stack.enter_async_context(
            stdio_client(server_params)
        )
        session = await connection_stack.enter_async_context(
            ClientSession(read, write)
        )
        
        return session
        
    def get_transport_info(self) -> str:
        return f"stdio:{self.server_config.command} {' '.join(self.server_config.args)}"


class WebSocketTransport(McpTransport):
    """MCP transport using WebSocket communication."""
    
    def __init__(self, server_config: 'McpServerConfig'):
        self.server_config = server_config
        
    async def create_session(self, connection_stack: AsyncExitStack) -> ClientSession:
        """Create WebSocket-based MCP session."""
        try:
            # Import websocket client - may not be available
            from mcp.client.websocket import websocket_client
        except ImportError as e:
            raise ImportError(
                "WebSocket transport requires additional dependencies. "
                "Install with: pip install 'mcp[websocket]'"
            ) from e
            
        # Create WebSocket connection
        websocket = await connection_stack.enter_async_context(
            websocket_client(
                url=self.server_config.url,
                headers=self.server_config.headers or {}
            )
        )
        
        # Create session with WebSocket
        session = await connection_stack.enter_async_context(
            ClientSession(websocket)
        )
        
        return session
        
    def get_transport_info(self) -> str:
        return f"websocket:{self.server_config.url}"


class HttpTransport(McpTransport):
    """MCP transport using HTTP communication."""
    
    def __init__(self, server_config: 'McpServerConfig'):
        self.server_config = server_config
        
    async def create_session(self, connection_stack: AsyncExitStack) -> ClientSession:
        """Create HTTP-based MCP session."""
        try:
            # Import HTTP client - may not be available
            from mcp.client.http import http_client
        except ImportError as e:
            raise ImportError(
                "HTTP transport requires additional dependencies. "
                "Install with: pip install 'mcp[http]'"
            ) from e
            
        # Prepare HTTP client configuration
        client_config = {
            'base_url': self.server_config.base_url,
            'timeout': self.server_config.timeout or 30
        }
        
        if self.server_config.api_key:
            client_config['headers'] = {
                'Authorization': f'Bearer {self.server_config.api_key}',
                **(self.server_config.headers or {})
            }
        elif self.server_config.headers:
            client_config['headers'] = self.server_config.headers
            
        # Create HTTP connection
        http_conn = await connection_stack.enter_async_context(
            http_client(**client_config)
        )
        
        # Create session with HTTP connection
        session = await connection_stack.enter_async_context(
            ClientSession(http_conn)
        )
        
        return session
        
    def get_transport_info(self) -> str:
        return f"http:{self.server_config.base_url}"


class McpTransportFactory:
    """Factory for creating MCP transport instances."""
    
    @staticmethod
    def create_transport(server_config: 'McpServerConfig') -> McpTransport:
        """Create appropriate transport based on server configuration."""
        transport_type = server_config.transport
        
        if transport_type == "stdio":
            return StdioTransport(server_config)
        elif transport_type == "websocket":
            return WebSocketTransport(server_config)
        elif transport_type == "http":
            return HttpTransport(server_config)
        else:
            raise ValueError(f"Unsupported transport type: {transport_type}")


class McpTool:
    """Wrapper for MCP tools to make them compatible with Semantic Kernel."""
    
    def __init__(self, name: str, description: str, input_schema: Dict[str, Any], client_session: ClientSession):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.client_session = client_session
        
        # Store original name for reference
        self.original_name = name
        
    async def invoke(self, **kwargs) -> str:
        """Invoke the MCP tool with the provided arguments."""
        try:
            # Validate inputs against schema if available
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
            # Enhanced error handling with transport-specific context
            error_msg = str(e).lower()
            transport_error_keywords = [
                'connection', 'session', 'closed', 'transport', 'websocket', 'http',
                'timeout', 'refused', 'unreachable', 'ssl', 'certificate'
            ]
            
            is_transport_error = any(keyword in error_msg for keyword in transport_error_keywords)
            
            if is_transport_error:
                # Try to find the client and mark as unhealthy
                from sk_agents.mcp_client import get_mcp_client
                mcp_client = get_mcp_client()
                for server_name, session in mcp_client.connected_servers.items():
                    if session == self.client_session:
                        mcp_client.mark_connection_unhealthy(server_name)
                        logger.warning(f"Marked MCP server '{server_name}' as unhealthy due to transport error")
                        break
                        
            logger.error(f"Error invoking MCP tool {self.name}: {e}")
            
            # Provide more specific error messages based on error type
            if 'timeout' in error_msg:
                raise RuntimeError(f"MCP tool '{self.name}' timed out. Check server responsiveness.") from e
            elif 'connection' in error_msg or 'refused' in error_msg:
                raise RuntimeError(f"MCP tool '{self.name}' connection failed. Check server availability.") from e
            elif 'ssl' in error_msg or 'certificate' in error_msg:
                raise RuntimeError(f"MCP tool '{self.name}' SSL/TLS error. Check certificates and encryption.") from e
            else:
                raise RuntimeError(f"MCP tool '{self.name}' failed: {e}") from e
            
    def _validate_inputs(self, kwargs: Dict[str, Any]) -> None:
        """Validate input arguments against the tool's JSON schema."""
        # Basic validation - could be enhanced with jsonschema library
        if not isinstance(self.input_schema, dict):
            return
            
        properties = self.input_schema.get('properties', {})
        required = self.input_schema.get('required', [])
        
        # Check required parameters
        for req_param in required:
            if req_param not in kwargs:
                raise ValueError(f"Missing required parameter '{req_param}' for tool '{self.name}'")
        
        # Check for unexpected parameters
        for param in kwargs:
            if param not in properties:
                logger.warning(f"Unexpected parameter '{param}' for tool '{self.name}'")


class McpPlugin(BasePlugin):
    """Plugin wrapper that holds MCP tools for Semantic Kernel integration."""
    
    def __init__(self, tools: List[McpTool], authorization: str | None = None, extra_data_collector=None):
        super().__init__(authorization, extra_data_collector)
        self.tools = tools
        
        # Dynamically add kernel functions for each tool
        for tool in tools:
            self._add_tool_function(tool)
    
    def _add_tool_function(self, tool: McpTool):
        """Add a tool as a kernel function to this plugin."""
        
        # Create a closure that captures the specific tool instance
        def create_tool_function(captured_tool: McpTool):
            @kernel_function(
                name=captured_tool.name,
                description=captured_tool.description,
            )
            async def tool_function(**kwargs):
                return await captured_tool.invoke(**kwargs)
            return tool_function
        
        # Create the function with the captured tool and set as attribute
        tool_function = create_tool_function(tool)
        
        # Sanitize tool name for Python attribute (replace invalid chars with underscore)
        attr_name = ''.join(c if c.isalnum() or c == '_' else '_' for c in tool.name)
        if not attr_name[0].isalpha() and attr_name[0] != '_':
            attr_name = f'tool_{attr_name}'
            
        setattr(self, attr_name, tool_function)


class McpClient:
    """
    MCP Client for connecting to MCP servers and registering their tools.
    
    This client handles the connection lifecycle to MCP servers, discovers available tools,
    and automatically registers them with the Semantic Kernel framework.
    """
    
    def __init__(self):
        """Initialize the MCP client."""
        self.connected_servers: Dict[str, ClientSession] = {}
        self.server_configs: Dict[str, McpServerConfig] = {}
        self.plugins: Dict[str, McpPlugin] = {}
        # Track connection resources for proper cleanup
        self._connection_stacks: Dict[str, AsyncExitStack] = {}
        self._connection_health: Dict[str, bool] = {}
        
    async def connect_server(self, server_config: McpServerConfig) -> None:
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
            # Create transport for the server configuration
            transport = McpTransportFactory.create_transport(server_config)
            transport_info = transport.get_transport_info()
            
            logger.info(f"Connecting to MCP server '{server_config.name}' via {transport_info}")
            
            # Create session using the transport
            session = await transport.create_session(connection_stack)
            
            # Initialize the session
            await session.initialize()
            
            # Store the session and resources
            self.connected_servers[server_config.name] = session
            self.server_configs[server_config.name] = server_config
            self._connection_stacks[server_config.name] = connection_stack
            self._connection_health[server_config.name] = True
            
            # Discover and register tools
            await self._discover_and_register_tools(server_config.name, session)
            
            logger.info(f"Successfully connected to MCP server: {server_config.name}")
            
        except Exception as e:
            # Cleanup on failure
            await connection_stack.aclose()
            
            # Provide transport-specific error context
            transport_type = server_config.transport
            error_msg = str(e).lower()
            
            if transport_type == "stdio":
                if 'permission' in error_msg or 'access' in error_msg:
                    logger.error(f"Permission denied for stdio MCP server '{server_config.name}': {e}")
                    raise ConnectionError(f"Permission denied. Check executable permissions for '{server_config.command}'") from e
                elif 'not found' in error_msg or 'no such file' in error_msg:
                    logger.error(f"Command not found for stdio MCP server '{server_config.name}': {e}")
                    raise ConnectionError(f"Command '{server_config.command}' not found. Check PATH or use absolute path.") from e
            elif transport_type == "websocket":
                if 'ssl' in error_msg or 'certificate' in error_msg:
                    logger.error(f"SSL/TLS error for WebSocket MCP server '{server_config.name}': {e}")
                    raise ConnectionError(f"WebSocket SSL/TLS error. Check certificate validity for '{server_config.url}'") from e
                elif 'timeout' in error_msg:
                    logger.error(f"Timeout connecting to WebSocket MCP server '{server_config.name}': {e}")
                    raise ConnectionError(f"WebSocket connection timeout. Check server availability at '{server_config.url}'") from e
            elif transport_type == "http":
                if '401' in error_msg or 'unauthorized' in error_msg:
                    logger.error(f"Authentication failed for HTTP MCP server '{server_config.name}': {e}")
                    raise ConnectionError(f"HTTP authentication failed. Check API key for '{server_config.base_url}'") from e
                elif '404' in error_msg or 'not found' in error_msg:
                    logger.error(f"HTTP endpoint not found for MCP server '{server_config.name}': {e}")
                    raise ConnectionError(f"HTTP endpoint not found. Check base_url '{server_config.base_url}'") from e
            
            # Generic error fallback
            logger.error(f"Failed to connect to {transport_type} MCP server '{server_config.name}': {e}")
            raise ConnectionError(f"Could not connect to {transport_type} MCP server '{server_config.name}': {e}") from e
    
    async def _discover_and_register_tools(self, server_name: str, session: ClientSession) -> None:
        """
        Discover tools from the connected MCP server and create plugin wrappers.
        
        Args:
            server_name: Name of the MCP server
            session: Active client session to the MCP server
        """
        try:
            # List available tools from the server
            tools_result = await session.list_tools()
            
            if not tools_result or not hasattr(tools_result, 'tools'):
                logger.warning(f"No tools found on MCP server: {server_name}")
                return
            
            # Create MCP tool wrappers
            mcp_tools = []
            for tool_info in tools_result.tools:
                mcp_tool = McpTool(
                    name=tool_info.name,
                    description=tool_info.description or f"Tool {tool_info.name} from {server_name}",
                    input_schema=getattr(tool_info, 'inputSchema', {}) or {},
                    client_session=session
                )
                mcp_tools.append(mcp_tool)
                
                logger.info(f"Discovered tool: {tool_info.name} from server {server_name}")
            
            # Create a plugin for this server's tools
            if mcp_tools:
                plugin = McpPlugin(mcp_tools)
                self.plugins[server_name] = plugin
                logger.info(f"Created plugin for server {server_name} with {len(mcp_tools)} tools")
            
        except Exception as e:
            logger.error(f"Failed to discover tools from MCP server {server_name}: {e}")
            raise
    
    def get_plugin(self, server_name: str) -> Optional[McpPlugin]:
        """
        Get the plugin for a specific MCP server.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            The plugin instance for the server, or None if not found
        """
        return self.plugins.get(server_name)
    
    def get_all_plugins(self) -> Dict[str, McpPlugin]:
        """
        Get all registered MCP plugins.
        
        Returns:
            Dictionary mapping server names to their plugins
        """
        return self.plugins.copy()
    
    def register_plugins_with_kernel(self, kernel: Kernel) -> None:
        """
        Register all MCP plugins with a Semantic Kernel instance.
        
        Args:
            kernel: The Semantic Kernel instance to register plugins with
        """
        for server_name, plugin in self.plugins.items():
            try:
                kernel.add_plugin(plugin, f"mcp_{server_name}")
                logger.info(f"Registered MCP plugin for server {server_name} with kernel")
            except Exception as e:
                logger.error(f"Failed to register MCP plugin for server {server_name}: {e}")
                raise
    
    async def disconnect_server(self, server_name: str) -> None:
        """
        Disconnect from an MCP server and clean up resources.
        
        Args:
            server_name: Name of the MCP server to disconnect from
        """
        try:
            # Clean up connection resources
            if server_name in self._connection_stacks:
                connection_stack = self._connection_stacks[server_name]
                await connection_stack.aclose()
                del self._connection_stacks[server_name]
                
            # Clean up tracking dictionaries
            if server_name in self.connected_servers:
                del self.connected_servers[server_name]
                
            if server_name in self.server_configs:
                del self.server_configs[server_name]
                
            if server_name in self.plugins:
                del self.plugins[server_name]
                
            if server_name in self._connection_health:
                del self._connection_health[server_name]
                
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
        """
        Check if connected to a specific MCP server.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            True if connected and healthy, False otherwise
        """
        return (
            server_name in self.connected_servers and 
            server_name in self._connection_health and
            self._connection_health[server_name]
        )
        
    def mark_connection_unhealthy(self, server_name: str) -> None:
        """
        Mark a connection as unhealthy (for use when tool invocations fail).
        
        Args:
            server_name: Name of the MCP server
        """
        if server_name in self._connection_health:
            self._connection_health[server_name] = False
            logger.warning(f"Marked MCP server {server_name} as unhealthy")
    
    def get_connected_servers(self) -> List[str]:
        """
        Get list of connected MCP server names.
        
        Returns:
            List of connected server names
        """
        return list(self.connected_servers.keys())


class McpClientManager:
    """Thread-safe singleton manager for MCP client instances."""
    
    _instance: Optional['McpClientManager'] = None
    _client: Optional[McpClient] = None
    _lock: Optional[asyncio.Lock] = None
    _thread_lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    async def get_client(self) -> McpClient:
        """Get or create the global MCP client instance (thread-safe)."""
        if self._client is None:
            # Initialize async lock if needed
            if self._lock is None:
                with self._thread_lock:
                    if self._lock is None:
                        self._lock = asyncio.Lock()
                        
            async with self._lock:
                # Double-check after acquiring lock
                if self._client is None:
                    self._client = McpClient()
        return self._client
    
    async def reset_client(self) -> None:
        """Reset the global MCP client instance (thread-safe)."""
        if self._lock is None:
            with self._thread_lock:
                if self._lock is None:
                    self._lock = asyncio.Lock()
                    
        async with self._lock:
            if self._client is not None:
                await self._client.disconnect_all()
                self._client = None


def get_mcp_client() -> McpClient:
    """
    Get the global MCP client instance.
    
    Note: This is a sync wrapper around async client management.
    In async contexts, consider using McpClientManager().get_client() directly.
    
    Returns:
        The global MCP client instance
    """
    manager = McpClientManager()
    
    # Try to get existing client first (fast path)
    if manager._client is not None:
        return manager._client
    
    # Need to create client - handle async context properly
    try:
        asyncio.get_running_loop()
        # We're in an async context but called sync function
        logger.warning(
            "get_mcp_client() called from async context. "
            "Consider using 'await McpClientManager().get_client()' instead."
        )
        # Create client synchronously for backward compatibility
        if manager._client is None:
            manager._client = McpClient()
        return manager._client
    except RuntimeError:
        # No event loop, safe to use asyncio.run()
        return asyncio.run(manager.get_client())