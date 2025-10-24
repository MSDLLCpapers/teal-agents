"""
MCP Plugin Registry - Materializes MCP plugin classes at session start.

This registry discovers MCP tools and creates plugin CLASSES (not instances),
making MCP tools behave like non-MCP code that exists in the codebase.

Per-user storage enables each user to have their own personalized tool set.
"""

import logging
import threading
from contextlib import AsyncExitStack
from typing import Any, Dict, List, Type

from sk_agents.mcp_client import (
    McpPlugin,
    McpTool,
    create_mcp_session,
    map_mcp_annotations_to_governance
)
from sk_agents.plugin_catalog.models import Governance, Oauth2PluginAuth, PluginTool
from sk_agents.plugin_catalog.plugin_catalog_factory import PluginCatalogFactory
from sk_agents.tealagents.v1alpha1.config import GovernanceOverride, McpServerConfig

logger = logging.getLogger(__name__)


class McpPluginRegistry:
    """
    Registry for MCP plugin classes with per-user storage.

    At session start (per user), this registry:
    1. Connects to MCP servers temporarily
    2. Discovers available tools (based on user's Arcade authorizations)
    3. Registers tools in catalog for governance/HITL
    4. Creates McpPlugin CLASSES containing stateless tools
    5. Stores classes per user for later instantiation (at agent build)

    This enables each user to have their own personalized tool set.
    """

    # Per-user plugin storage: {user_id: {server_name: plugin_class}}
    _plugin_classes_per_user: Dict[str, Dict[str, Type]] = {}
    _lock = threading.Lock()

    @staticmethod
    def _apply_governance_overrides(
        base_governance: Governance,
        tool_name: str,
        overrides: Dict[str, GovernanceOverride] | None
    ) -> Governance:
        """Apply manual governance overrides from config."""
        if not overrides or tool_name not in overrides:
            return base_governance

        override = overrides[tool_name]

        return Governance(
            requires_hitl=override.requires_hitl if override.requires_hitl is not None else base_governance.requires_hitl,
            cost=override.cost if override.cost is not None else base_governance.cost,
            data_sensitivity=override.data_sensitivity if override.data_sensitivity is not None else base_governance.data_sensitivity
        )

    @staticmethod
    def _create_auth_if_needed(server_config: McpServerConfig) -> Oauth2PluginAuth | None:
        """Create auth config if server requires OAuth2."""
        if server_config.auth_server and server_config.scopes:
            return Oauth2PluginAuth(
                auth_server=server_config.auth_server,
                scopes=server_config.scopes
            )
        return None

    @classmethod
    async def discover_and_materialize(
        cls,
        mcp_servers: List[McpServerConfig],
        user_id: str
    ) -> None:
        """
        Discover MCP tools and materialize plugin classes for specific user.

        Each user gets their own plugin classes based on tools they can access
        (determined by Arcade authorizations, MCP server permissions, etc.)

        Args:
            mcp_servers: List of MCP server configurations
            user_id: User ID for authentication and tool discovery
        """
        logger.info(f"Starting MCP discovery for user {user_id} ({len(mcp_servers)} servers)")

        # Initialize user's plugin dictionary if needed
        with cls._lock:
            if user_id not in cls._plugin_classes_per_user:
                cls._plugin_classes_per_user[user_id] = {}

        for server_config in mcp_servers:
            try:
                await cls._discover_server(server_config, user_id)
            except Exception as e:
                logger.error(f"Failed to discover MCP server {server_config.name} for user {user_id}: {e}")
                # Continue with other servers
                continue

        user_plugin_count = len(cls._plugin_classes_per_user.get(user_id, {}))
        logger.info(f"MCP discovery complete for user {user_id}. Materialized {user_plugin_count} plugin classes")

    @classmethod
    async def _discover_server(cls, server_config: McpServerConfig, user_id: str) -> None:
        """Discover tools from a single MCP server."""
        logger.info(f"Discovering tools from MCP server: {server_config.name} for user {user_id}")

        # Temporary connection for discovery
        async with AsyncExitStack() as stack:
            # Create temp connection
            session = await create_mcp_session(server_config, stack, user_id)
            await session.initialize()

            # List available tools
            tools_result = await session.list_tools()
            logger.info(f"Found {len(tools_result.tools)} tools on {server_config.name} for user {user_id}")

            # Create stateless McpTool objects
            mcp_tools = []
            for tool_info in tools_result.tools:
                # Create stateless tool
                mcp_tool = McpTool(
                    tool_name=tool_info.name,
                    description=tool_info.description,
                    input_schema=tool_info.inputSchema,
                    output_schema=getattr(tool_info, 'outputSchema', None),
                    server_config=server_config,
                    server_name=server_config.name,
                    user_id=user_id
                )
                mcp_tools.append(mcp_tool)

                # Register in catalog for governance/HITL
                cls._register_tool_in_catalog(tool_info, server_config)

            # Create McpPlugin CLASS (not instance!)
            plugin_class = cls._create_plugin_class(mcp_tools, server_config.name)

            # Store the class for THIS user
            with cls._lock:
                cls._plugin_classes_per_user[user_id][server_config.name] = plugin_class

            logger.info(f"Materialized McpPlugin class for {server_config.name} (user: {user_id})")
            # Connection auto-closes when exiting context

    @classmethod
    def _register_tool_in_catalog(cls, tool_info: Any, server_config: McpServerConfig) -> None:
        """Register tool in catalog for governance and HITL."""
        try:
            catalog = PluginCatalogFactory().get_catalog()
            if not catalog:
                logger.warning("Plugin catalog not available, skipping catalog registration")
                return

            # Create consistent tool_id format
            tool_id = f"mcp_{server_config.name}-{server_config.name}_{tool_info.name}"

            # Map MCP annotations to governance
            annotations = getattr(tool_info, 'annotations', {}) or {}
            base_governance = map_mcp_annotations_to_governance(annotations)

            # Apply manual overrides from config
            governance = cls._apply_governance_overrides(
                base_governance,
                tool_info.name,
                server_config.tool_governance_overrides
            )

            # Create auth config if needed
            auth = cls._create_auth_if_needed(server_config)

            # Create PluginTool for catalog
            plugin_tool = PluginTool(
                tool_id=tool_id,
                name=tool_info.name,
                description=tool_info.description,
                governance=governance,
                auth=auth
            )

            # Register in catalog
            plugin_id = f"mcp_{server_config.name}"
            catalog.register_dynamic_tool(plugin_tool, plugin_id=plugin_id)

            logger.debug(f"Registered tool in catalog: {tool_id} (requires_hitl={governance.requires_hitl})")

        except Exception as e:
            logger.error(f"Failed to register tool {tool_info.name} in catalog: {e}")
            # Don't fail the whole discovery if catalog registration fails

    @classmethod
    def _create_plugin_class(cls, tools: List[McpTool], server_name: str) -> Type:
        """
        Create a McpPlugin class dynamically.

        This is like having WeatherPlugin.py in the codebase - the class exists
        and can be instantiated multiple times.
        """
        def create_class(tools_list, srv_name):
            class DynamicMcpPlugin(McpPlugin):
                def __init__(self, authorization=None, extra_data_collector=None):
                    super().__init__(
                        tools=tools_list,
                        server_name=srv_name,
                        authorization=authorization,
                        extra_data_collector=extra_data_collector
                    )

            # Set a meaningful class name
            DynamicMcpPlugin.__name__ = f"McpPlugin_{srv_name}"
            DynamicMcpPlugin.__qualname__ = f"McpPlugin_{srv_name}"

            return DynamicMcpPlugin

        return create_class(tools, server_name)

    @classmethod
    def get_plugin_class(cls, server_name: str, user_id: str) -> Type | None:
        """
        Get MCP plugin class for a specific user and server.

        This is like loading a plugin class from a file in non-MCP tools,
        but retrieves the user-specific version.

        Args:
            server_name: Name of the MCP server
            user_id: User ID whose plugins to retrieve

        Returns:
            Plugin class if available for this user, None otherwise
        """
        with cls._lock:
            user_plugins = cls._plugin_classes_per_user.get(user_id, {})
            return user_plugins.get(server_name)

    @classmethod
    def get_all_plugin_classes_for_user(cls, user_id: str) -> Dict[str, Type]:
        """
        Get all MCP plugin classes for a specific user.
        
        Args:
            user_id: User ID whose plugins to retrieve
            
        Returns:
            Dictionary of {server_name: plugin_class} for this user
        """
        with cls._lock:
            return cls._plugin_classes_per_user.get(user_id, {}).copy()
    
    @classmethod
    def clear_user_plugins(cls, user_id: str) -> None:
        """
        Clear plugin classes for a specific user.
        
        Call this after user authorizes new providers to trigger re-discovery.
        
        Args:
            user_id: User ID whose plugins to clear
        """
        with cls._lock:
            if user_id in cls._plugin_classes_per_user:
                del cls._plugin_classes_per_user[user_id]
                logger.info(f"Cleared MCP plugin cache for user: {user_id}")

    @classmethod
    def clear(cls) -> None:
        """Clear all registered plugin classes (for testing)."""
        with cls._lock:
            cls._plugin_classes_per_user.clear()

