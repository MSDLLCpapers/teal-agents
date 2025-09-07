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


logger = logging.getLogger(__name__)


async def create_mcp_session(server_config: McpServerConfig, connection_stack: AsyncExitStack) -> ClientSession:
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
        # Try streamable HTTP first (preferred), fall back to SSE
        try:
            from mcp.client.streamable_http import streamablehttp_client
            
            # Use streamable HTTP transport
            read, write, _ = await connection_stack.enter_async_context(
                streamablehttp_client(
                    url=server_config.url,
                    headers=server_config.headers,
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
                        headers=server_config.headers,
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
    
    def __init__(self, name: str, description: str, input_schema: Dict[str, Any], client_session):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.client_session = client_session
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
            # Get transport info for logging
            transport_info = get_transport_info(server_config)
            logger.info(f"Connecting to MCP server '{server_config.name}' via {transport_info}")
            
            # Create session using MCP SDK
            session = await create_mcp_session(server_config, connection_stack)
            
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
    
    async def _discover_and_register_tools(self, server_name: str, session) -> None:
        """Discover tools from the connected MCP server and create plugin wrappers."""
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
                plugin = McpPlugin(mcp_tools, server_name=server_name)
                self.plugins[server_name] = plugin
                logger.info(f"Created plugin for server {server_name} with {len(mcp_tools)} tools")
            
        except Exception as e:
            logger.error(f"Failed to discover tools from MCP server {server_name}: {e}")
            raise
    
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
    
    async def disconnect_server(self, server_name: str) -> None:
        """Disconnect from an MCP server and clean up resources."""
        try:
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
    """Get the global MCP client instance."""
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