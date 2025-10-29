"""
MCP Plugin Registry - Materializes MCP plugin classes at session start.

This registry discovers MCP tools and creates plugin CLASSES (not instances),
making MCP tools behave like non-MCP code that exists in the codebase.
"""

import logging
import threading
from contextlib import AsyncExitStack
from typing import Any, Dict, List

from sk_agents.mcp_client import (
    McpPlugin,
    McpTool,
    apply_trust_level_governance,
    create_mcp_session,
    map_mcp_annotations_to_governance,
)
from sk_agents.plugin_catalog.models import Governance, Oauth2PluginAuth, PluginTool
from sk_agents.plugin_catalog.plugin_catalog_factory import PluginCatalogFactory
from sk_agents.tealagents.v1alpha1.config import GovernanceOverride, McpServerConfig

logger = logging.getLogger(__name__)


class McpPluginRegistry:
    """
    Registry for MCP plugin classes.

    At session start, this registry:
    1. Connects to MCP servers temporarily
    2. Discovers available tools
    3. Registers tools in catalog for governance/HITL
    4. Creates McpPlugin CLASSES containing stateless tools
    5. Stores classes for later instantiation (at agent build)

    This makes MCP tools work like non-MCP tools that exist as code.
    """

    _plugin_classes: Dict[str, type] = {}  # Key: server_name, Value: McpPlugin class
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
        Discover MCP tools and materialize plugin classes.

        This is called ONCE at session/application start.
        Creates temporary connections to discover tools, then closes them.

        Args:
            mcp_servers: List of MCP server configurations
            user_id: User ID for authentication

        Raises:
            AuthRequiredError: If any server requires authentication that is missing
        """
        from sk_agents.mcp_client import AuthRequiredError

        logger.info(f"Starting MCP discovery for {len(mcp_servers)} servers")

        auth_errors = []  # Collect auth errors to surface to user

        for server_config in mcp_servers:
            try:
                await cls._discover_server(server_config, user_id)
            except AuthRequiredError as e:
                # Auth error - collect and surface to user
                logger.warning(f"Auth required for MCP server {server_config.name}")
                auth_errors.append(e)
            except Exception as e:
                # Other errors - log and continue with remaining servers
                logger.error(f"Failed to discover MCP server {server_config.name}: {e}")
                continue

        # If any servers require auth, raise the first one to trigger auth challenge
        if auth_errors:
            logger.info(
                f"MCP discovery requires authentication for {len(auth_errors)} server(s): "
                f"{[e.server_name for e in auth_errors]}"
            )
            raise auth_errors[0]  # Raise first auth error to trigger challenge

        logger.info(f"MCP discovery complete. Materialized {len(cls._plugin_classes)} plugin classes")

    @classmethod
    async def _discover_server(cls, server_config: McpServerConfig, user_id: str) -> None:
        """Discover tools from a single MCP server."""
        logger.info(f"Discovering tools from MCP server: {server_config.name}")

        # Pre-flight auth validation: Check if user has auth before attempting discovery
        if server_config.auth_server and server_config.scopes:
            from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
            from sk_agents.mcp_client import build_auth_storage_key, AuthRequiredError
            from ska_utils import AppConfig
            from datetime import datetime, timezone

            # Check if user has valid auth token
            auth_storage_factory = AuthStorageFactory(AppConfig())
            auth_storage = auth_storage_factory.get_auth_storage_manager()

            composite_key = build_auth_storage_key(
                server_config.auth_server,
                server_config.scopes
            )
            auth_data = auth_storage.retrieve(user_id, composite_key)

            if not auth_data:
                logger.warning(
                    f"Auth required for {server_config.name}: No token found for user {user_id}"
                )
                raise AuthRequiredError(
                    server_name=server_config.name,
                    auth_server=server_config.auth_server,
                    scopes=server_config.scopes
                )

            # Validate token expiry
            if auth_data.expires_at <= datetime.now(timezone.utc):
                logger.warning(
                    f"Auth required for {server_config.name}: Token expired at {auth_data.expires_at}"
                )
                raise AuthRequiredError(
                    server_name=server_config.name,
                    auth_server=server_config.auth_server,
                    scopes=server_config.scopes,
                    message=f"Token expired for MCP server '{server_config.name}'"
                )

            logger.info(f"Auth verified for {server_config.name}, proceeding with discovery")

        # Temporary connection for discovery
        async with AsyncExitStack() as stack:
            # Create temp connection
            session = await create_mcp_session(server_config, stack, user_id)

            # List available tools
            tools_result = await session.list_tools()
            logger.info(f"Found {len(tools_result.tools)} tools on {server_config.name}")

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
                )
                mcp_tools.append(mcp_tool)

                # Register in catalog for governance/HITL
                cls._register_tool_in_catalog(tool_info, server_config)

            # Create McpPlugin CLASS (not instance!)
            plugin_class = cls._create_plugin_class(mcp_tools, server_config.name)

            # Store the class
            with cls._lock:
                cls._plugin_classes[server_config.name] = plugin_class

            logger.info(f"Materialized McpPlugin class for {server_config.name}")
            # Connection auto-closes when exiting context

    @classmethod
    def _register_tool_in_catalog(cls, tool_info: Any, server_config: McpServerConfig) -> None:
        """Register tool in catalog for governance and HITL."""
        try:
            catalog = PluginCatalogFactory().get_catalog()
            if not catalog:
                logger.warning("Plugin catalog not available, skipping catalog registration")
                return

            # Create consistent tool_id format: mcp_{server_name}_{tool_name}
            tool_id = f"mcp_{server_config.name}_{tool_info.name}"

            # Map MCP annotations to governance
            annotations = getattr(tool_info, 'annotations', {}) or {}
            base_governance = map_mcp_annotations_to_governance(annotations)
            governance_with_trust = apply_trust_level_governance(
                base_governance,
                server_config.trust_level,
                tool_info.description or ""
            )

            # Apply manual overrides from config
            governance = cls._apply_governance_overrides(
                governance_with_trust,
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
    def _create_plugin_class(cls, tools: List[McpTool], server_name: str) -> type:
        """
        Create a McpPlugin class dynamically.

        This is like having WeatherPlugin.py in the codebase - the class exists
        and can be instantiated multiple times.
        """
        def create_class(tools_list, srv_name):
            class DynamicMcpPlugin(McpPlugin):
                def __init__(self, user_id: str, authorization=None, extra_data_collector=None):
                    super().__init__(
                        tools=tools_list,
                        server_name=srv_name,
                        user_id=user_id,
                        authorization=authorization,
                        extra_data_collector=extra_data_collector
                    )

            # Set a meaningful class name
            DynamicMcpPlugin.__name__ = f"McpPlugin_{srv_name}"
            DynamicMcpPlugin.__qualname__ = f"McpPlugin_{srv_name}"

            return DynamicMcpPlugin

        return create_class(tools, server_name)

    @classmethod
    def get_plugin_class(cls, server_name: str) -> type | None:
        """
        Get MCP plugin class for a server.

        This is like loading a plugin class from a file in non-MCP tools.

        Args:
            server_name: Name of the MCP server

        Returns:
            Plugin class if available, None otherwise
        """
        with cls._lock:
            return cls._plugin_classes.get(server_name)

    @classmethod
    def get_all_plugin_classes(cls) -> Dict[str, type]:
        """Get all available MCP plugin classes."""
        with cls._lock:
            return cls._plugin_classes.copy()

    @classmethod
    def clear(cls) -> None:
        """Clear all registered plugin classes (for testing)."""
        with cls._lock:
            cls._plugin_classes.clear()
