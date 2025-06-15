"""MCP (Model Context Protocol) integration for Teal Agents platform.

This module provides MCP client capabilities that can be used as Semantic Kernel plugins,
allowing Teal Agents to connect to and interact with MCP servers.
"""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from semantic_kernel.functions import kernel_function
from semantic_kernel.functions.kernel_function_decorator import kernel_function
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class MCPServerConfig(BaseModel):
    """Configuration for an MCP server connection."""
    
    name: str = Field(description="Name identifier for the MCP server")
    command: str = Field(description="Command to start the MCP server")
    args: List[str] = Field(default_factory=list, description="Arguments for the MCP server command")
    env: Dict[str, str] = Field(default_factory=dict, description="Environment variables for the MCP server")
    timeout: int = Field(default=30, description="Connection timeout in seconds")


class MCPToolResult(BaseModel):
    """Result from an MCP tool call."""
    
    success: bool
    content: str
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MCPPlugin:
    """Semantic Kernel plugin that provides MCP server connectivity."""
    
    def __init__(self, server_configs: List[MCPServerConfig]):
        """Initialize MCP plugin with server configurations.
        
        Args:
            server_configs: List of MCP server configurations to connect to
        """
        self.server_configs = {config.name: config for config in server_configs}
        self.sessions: Dict[str, ClientSession] = {}
        self.connections: Dict[str, Any] = {}
        self._initialized = False
    
    async def initialize(self):
        """Initialize connections to all configured MCP servers."""
        if self._initialized:
            return
            
        for server_name, config in self.server_configs.items():
            try:
                await self._connect_to_server(server_name, config)
                logger.info(f"Connected to MCP server: {server_name}")
            except Exception as e:
                logger.error(f"Failed to connect to MCP server {server_name}: {e}")
        
        self._initialized = True
    
    async def _connect_to_server(self, server_name: str, config: MCPServerConfig):
        """Connect to a single MCP server."""
        try:
            server_params = StdioServerParameters(
                command=config.command,
                args=config.args,
                env=config.env
            )
            
            # Establish connection with timeout
            stdio_context = stdio_client(server_params)
            read, write = await asyncio.wait_for(
                stdio_context.__aenter__(), 
                timeout=config.timeout
            )
            
            session_context = ClientSession(read, write)
            session = await asyncio.wait_for(
                session_context.__aenter__(),
                timeout=config.timeout
            )
            
            await asyncio.wait_for(
                session.initialize(),
                timeout=config.timeout
            )
            
            # Store connection details
            self.connections[server_name] = (stdio_context, session_context)
            self.sessions[server_name] = session
            
        except asyncio.TimeoutError:
            logger.error(f"Timeout connecting to MCP server {server_name} after {config.timeout}s")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to MCP server {server_name}: {e}")
            raise
    
    async def cleanup(self):
        """Clean up all MCP server connections."""
        for server_name in list(self.sessions.keys()):
            try:
                # Clean up session
                if server_name in self.sessions:
                    session = self.sessions[server_name]
                    if hasattr(session, '__aexit__'):
                        await session.__aexit__(None, None, None)
                
                # Clean up connection contexts
                if server_name in self.connections:
                    stdio_context, session_context = self.connections[server_name]
                    if hasattr(session_context, '__aexit__'):
                        await session_context.__aexit__(None, None, None)
                    if hasattr(stdio_context, '__aexit__'):
                        await stdio_context.__aexit__(None, None, None)
                
                logger.info(f"Disconnected from MCP server: {server_name}")
            except Exception as e:
                logger.error(f"Error disconnecting from MCP server {server_name}: {e}")
        
        self.sessions.clear()
        self.connections.clear()
        self._initialized = False
    
    @kernel_function(
        name="list_mcp_tools",
        description="List all available tools from connected MCP servers"
    )
    async def list_mcp_tools(self) -> str:
        """List all available MCP tools from connected servers."""
        if not self._initialized:
            await self.initialize()
        
        all_tools = {}
        
        for server_name, session in self.sessions.items():
            try:
                tools_response = await session.list_tools()
                server_tools = []
                
                for tool in tools_response.tools:
                    server_tools.append({
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.inputSchema
                    })
                
                all_tools[server_name] = server_tools
            except Exception as e:
                logger.error(f"Error listing tools from {server_name}: {e}")
                all_tools[server_name] = {"error": str(e)}
        
        return json.dumps(all_tools, indent=2)
    
    @kernel_function(
        name="call_mcp_tool",
        description="Call a specific tool on an MCP server"
    )
    async def call_mcp_tool(
        self, 
        server_name: str, 
        tool_name: str, 
        arguments: str = "{}"
    ) -> str:
        """Call a specific MCP tool with given arguments.
        
        Args:
            server_name: Name of the MCP server
            tool_name: Name of the tool to call
            arguments: JSON string of tool arguments
            
        Returns:
            JSON string containing the tool result
        """
        if not self._initialized:
            await self.initialize()
        
        if server_name not in self.sessions:
            return json.dumps({
                "success": False,
                "error": f"MCP server '{server_name}' not found or not connected"
            })
        
        try:
            # Parse arguments
            args_dict = json.loads(arguments) if arguments else {}
            
            # Call the tool
            session = self.sessions[server_name]
            result = await session.call_tool(tool_name, arguments=args_dict)
            
            # Format response
            content_parts = []
            for content in result.content:
                if hasattr(content, 'text'):
                    content_parts.append(content.text)
                else:
                    content_parts.append(str(content))
            
            response = MCPToolResult(
                success=True,
                content="\n".join(content_parts),
                metadata={
                    "server": server_name,
                    "tool": tool_name,
                    "is_error": result.isError if hasattr(result, 'isError') else False
                }
            )
            
        except Exception as e:
            logger.error(f"Error calling MCP tool {tool_name} on {server_name}: {e}")
            response = MCPToolResult(
                success=False,
                content="",
                error=str(e),
                metadata={"server": server_name, "tool": tool_name}
            )
        
        return response.model_dump_json()
    
    @kernel_function(
        name="read_mcp_resource",
        description="Read a resource from an MCP server"
    )
    async def read_mcp_resource(self, server_name: str, resource_uri: str) -> str:
        """Read a resource from an MCP server.
        
        Args:
            server_name: Name of the MCP server
            resource_uri: URI of the resource to read
            
        Returns:
            JSON string containing the resource content
        """
        if not self._initialized:
            await self.initialize()
        
        if server_name not in self.sessions:
            return json.dumps({
                "success": False,
                "error": f"MCP server '{server_name}' not found or not connected"
            })
        
        try:
            session = self.sessions[server_name]
            result = await session.read_resource(resource_uri)
            
            content_parts = []
            for content in result.contents:
                if hasattr(content, 'text'):
                    content_parts.append(content.text)
                else:
                    content_parts.append(str(content))
            
            response = {
                "success": True,
                "content": "\n".join(content_parts),
                "uri": resource_uri,
                "server": server_name
            }
            
        except Exception as e:
            logger.error(f"Error reading resource {resource_uri} from {server_name}: {e}")
            response = {
                "success": False,
                "error": str(e),
                "uri": resource_uri,
                "server": server_name
            }
        
        return json.dumps(response, indent=2)
    
    @kernel_function(
        name="get_mcp_prompt",
        description="Get a prompt template from an MCP server"
    )
    async def get_mcp_prompt(
        self, 
        server_name: str, 
        prompt_name: str, 
        arguments: str = "{}"
    ) -> str:
        """Get a prompt template from an MCP server.
        
        Args:
            server_name: Name of the MCP server
            prompt_name: Name of the prompt to get
            arguments: JSON string of prompt arguments
            
        Returns:
            JSON string containing the prompt content
        """
        if not self._initialized:
            await self.initialize()
        
        if server_name not in self.sessions:
            return json.dumps({
                "success": False,
                "error": f"MCP server '{server_name}' not found or not connected"
            })
        
        try:
            args_dict = json.loads(arguments) if arguments else {}
            
            session = self.sessions[server_name]
            result = await session.get_prompt(prompt_name, arguments=args_dict)
            
            response = {
                "success": True,
                "name": prompt_name,
                "description": result.description,
                "messages": [
                    {
                        "role": msg.role,
                        "content": msg.content.text if hasattr(msg.content, 'text') else str(msg.content)
                    }
                    for msg in result.messages
                ],
                "server": server_name
            }
            
        except Exception as e:
            logger.error(f"Error getting prompt {prompt_name} from {server_name}: {e}")
            response = {
                "success": False,
                "error": str(e),
                "name": prompt_name,
                "server": server_name
            }
        
        return json.dumps(response, indent=2)


class MCPPluginFactory:
    """Factory for creating MCP plugins from configuration."""
    
    @staticmethod
    def create_from_config(mcp_configs: List[Dict[str, Any]]) -> MCPPlugin:
        """Create MCP plugin from configuration dictionaries.
        
        Args:
            mcp_configs: List of MCP server configuration dictionaries
            
        Returns:
            Configured MCPPlugin instance
        """
        server_configs = [MCPServerConfig(**config) for config in mcp_configs]
        return MCPPlugin(server_configs)
    
    @staticmethod
    def create_filesystem_plugin(workspace_path: str = "/workspace") -> MCPPlugin:
        """Create MCP plugin with filesystem server.
        
        Args:
            workspace_path: Path to workspace directory
            
        Returns:
            MCPPlugin configured with filesystem server
        """
        config = MCPServerConfig(
            name="filesystem",
            command="npx",
            args=["@modelcontextprotocol/server-filesystem", workspace_path],
            env={}
        )
        return MCPPlugin([config])
    
    @staticmethod
    def create_sqlite_plugin(db_path: str) -> MCPPlugin:
        """Create MCP plugin with SQLite server.
        
        Args:
            db_path: Path to SQLite database file
            
        Returns:
            MCPPlugin configured with SQLite server
        """
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        wrapper_script = os.path.join(script_dir, "..", "..", "run_sqlite_mcp_server.py")
        
        config = MCPServerConfig(
            name="sqlite",
            command="python",  
            args=[wrapper_script, db_path],
            env={}
        )
        return MCPPlugin([config])