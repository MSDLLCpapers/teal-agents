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
        user_id: str
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
            user_id: User ID for authentication
        """
        self.tool_name = tool_name
        self.description = description
        self.input_schema = input_schema
        self.output_schema = output_schema
        self.server_config = server_config
        self.server_name = server_name
        self.user_id = user_id

    async def invoke(self, **kwargs) -> str:
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
                    self.user_id
                )
                await session.initialize()

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
    """

    def __init__(
        self,
        tools: List[McpTool],
        server_name: str,
        authorization: str | None = None,
        extra_data_collector=None
    ):
        super().__init__(authorization, extra_data_collector)
        self.tools = tools
        self.server_name = server_name

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
                return await captured_tool.invoke(**kwargs)

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
