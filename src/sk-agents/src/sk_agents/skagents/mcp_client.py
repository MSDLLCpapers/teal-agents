"""
MCP Client for Teal Agents Platform.

This module provides an MCP (Model Context Protocol) client that can connect to MCP servers
and automatically register their tools with the Semantic Kernel framework.
"""

import logging
from typing import Any, Dict, List, Optional

from semantic_kernel.functions import kernel_function

from sk_agents.ska_types import BasePlugin


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