"""
MCP Client for Teal Agents Platform.

This module provides an MCP (Model Context Protocol) client that can connect to MCP servers
and automatically register their tools with the Semantic Kernel framework.
"""

import logging
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from semantic_kernel.functions import kernel_function
from semantic_kernel.kernel import Kernel

from sk_agents.ska_types import BasePlugin
from sk_agents.tealagents.v1alpha1.config import McpServerConfig


logger = logging.getLogger(__name__)


class McpTool:
    """Wrapper for MCP tools to make them compatible with Semantic Kernel."""
    
    def __init__(self, name: str, description: str, input_schema: Dict[str, Any], client_session: ClientSession):
        self.name = name
        self.description = description
        self.input_schema = input_schema
        self.client_session = client_session
        
    async def invoke(self, **kwargs) -> str:
        """Invoke the MCP tool with the provided arguments."""
        try:
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
            raise


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
        
        # Create a kernel function wrapper for the MCP tool
        @kernel_function(
            name=tool.name,
            description=tool.description,
        )
        async def tool_function(**kwargs):
            return await tool.invoke(**kwargs)
        
        # Set the function as an attribute of this plugin
        setattr(self, tool.name, tool_function)


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
        
    async def connect_server(self, server_config: McpServerConfig) -> None:
        """
        Connect to an MCP server and register its tools.
        
        Args:
            server_config: Configuration for the MCP server to connect to
            
        Raises:
            ConnectionError: If connection to the MCP server fails
            ValueError: If server configuration is invalid
        """
        try:
            logger.info(f"Connecting to MCP server: {server_config.name}")
            
            # Create server parameters
            server_params = StdioServerParameters(
                command=server_config.command,
                args=server_config.args,
                env=server_config.env or {}
            )
            
            # Connect to the server
            async with stdio_client(server_params) as (read, write):
                async with ClientSession(read, write) as session:
                    # Initialize the session
                    await session.initialize()
                    
                    # Store the session
                    self.connected_servers[server_config.name] = session
                    self.server_configs[server_config.name] = server_config
                    
                    # Discover and register tools
                    await self._discover_and_register_tools(server_config.name, session)
                    
                    logger.info(f"Successfully connected to MCP server: {server_config.name}")
                    
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_config.name}: {e}")
            raise ConnectionError(f"Could not connect to MCP server {server_config.name}: {e}") from e
    
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
            if server_name in self.connected_servers:
                # Clean up the session (session cleanup happens automatically with context manager)
                del self.connected_servers[server_name]
                
            if server_name in self.server_configs:
                del self.server_configs[server_name]
                
            if server_name in self.plugins:
                del self.plugins[server_name]
                
            logger.info(f"Disconnected from MCP server: {server_name}")
            
        except Exception as e:
            logger.error(f"Error disconnecting from MCP server {server_name}: {e}")
    
    async def disconnect_all(self) -> None:
        """Disconnect from all connected MCP servers."""
        server_names = list(self.connected_servers.keys())
        for server_name in server_names:
            await self.disconnect_server(server_name)
    
    def is_connected(self, server_name: str) -> bool:
        """
        Check if connected to a specific MCP server.
        
        Args:
            server_name: Name of the MCP server
            
        Returns:
            True if connected, False otherwise
        """
        return server_name in self.connected_servers
    
    def get_connected_servers(self) -> List[str]:
        """
        Get list of connected MCP server names.
        
        Returns:
            List of connected server names
        """
        return list(self.connected_servers.keys())


class McpClientManager:
    """Singleton manager for MCP client instances."""
    
    _instance: Optional['McpClientManager'] = None
    _client: Optional[McpClient] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def get_client(self) -> McpClient:
        """Get or create the global MCP client instance."""
        if self._client is None:
            self._client = McpClient()
        return self._client
    
    def reset_client(self) -> None:
        """Reset the global MCP client instance."""
        self._client = None


def get_mcp_client() -> McpClient:
    """
    Get the global MCP client instance.
    
    Returns:
        The global MCP client instance
    """
    manager = McpClientManager()
    return manager.get_client()