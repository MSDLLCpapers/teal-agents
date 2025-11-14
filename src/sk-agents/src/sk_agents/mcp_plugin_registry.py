"""
MCP Plugin Registry - Materializes MCP plugin classes at session start.

This registry discovers MCP tools and creates plugin CLASSES (not instances),
making MCP tools behave like non-MCP code that exists in the codebase.
"""

import logging
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
    Registry for MCP plugin classes with per-session isolation.

    At session start, this registry:
    1. Connects to MCP servers temporarily
    2. Discovers available tools
    3. Registers tools in catalog for governance/HITL
    4. Serializes plugin data to external storage (via McpDiscoveryManager)
    5. Plugin classes reconstructed from storage at agent build time

    This ensures proper multi-tenant isolation and horizontal scalability.
    Plugin state is stored externally (Redis/InMemory) instead of class variables.
    """

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
        user_id: str,
        session_id: str,
        discovery_manager,  # McpDiscoveryManager
    ) -> None:
        """
        Discover MCP tools and store in external state.

        This is called once per session when first invoked.
        Creates temporary connections to discover tools, then closes them.

        Args:
            mcp_servers: List of MCP server configurations
            user_id: User ID for authentication
            session_id: Session ID for scoping
            discovery_manager: Manager for storing discovery state

        Raises:
            AuthRequiredError: If any server requires authentication that is missing
        """
        from sk_agents.mcp_client import AuthRequiredError

        logger.info(f"Starting MCP discovery for session {session_id} ({len(mcp_servers)} servers)")

        # Load existing state
        state = await discovery_manager.load_discovery(user_id, session_id)
        if not state:
            raise ValueError(f"Discovery state not initialized for session: {session_id}")

        auth_errors = []  # Collect auth errors to surface to user

        for server_config in mcp_servers:
            try:
                # Discover this server
                plugin_data = await cls._discover_server(server_config, user_id)

                # Store serialized plugin data
                state.discovered_servers[server_config.name] = plugin_data

                # Update external storage
                await discovery_manager.update_discovery(state)

            except AuthRequiredError as e:
                # Auth error - collect and surface to user
                logger.warning(f"Auth required for MCP server {server_config.name} (session: {session_id})")
                auth_errors.append(e)
            except Exception as e:
                # Other errors - log and continue with remaining servers
                logger.error(f"Failed to discover MCP server {server_config.name} for session {session_id}: {e}")
                continue

        # If any servers require auth, raise the first one to trigger auth challenge
        if auth_errors:
            logger.info(
                f"MCP discovery requires authentication for {len(auth_errors)} server(s) (session: {session_id}): "
                f"{[e.server_name for e in auth_errors]}"
            )
            raise auth_errors[0]  # Raise first auth error to trigger challenge

        logger.info(f"MCP discovery complete for session {session_id}. Discovered {len(state.discovered_servers)} servers")

    @classmethod
    async def _discover_server(cls, server_config: McpServerConfig, user_id: str) -> Dict:
        """
        Discover tools from a single MCP server.

        Returns:
            Dict: Serialized plugin data for storage
        """
        logger.info(f"Discovering tools from MCP server: {server_config.name}")

        # Pre-flight auth validation: Only for OAuth-configured servers
        # For simple header auth, no pre-flight check needed (credentials in headers)
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

            # Serialize plugin data for storage
            plugin_data = cls._serialize_plugin_data(mcp_tools, server_config.name)

            logger.info(f"Discovered {len(mcp_tools)} tools from {server_config.name}")
            # Connection auto-closes when exiting context

            return plugin_data

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
    def _serialize_plugin_data(cls, tools: List[McpTool], server_name: str) -> Dict:
        """
        Serialize plugin tools to storable format.

        Args:
            tools: List of McpTool objects
            server_name: Name of the MCP server

        Returns:
            Dict: Serialized plugin data
        """
        tools_data = []
        for tool in tools:
            tools_data.append(
                {
                    "tool_name": tool.tool_name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
                    "server_name": tool.server_name,
                    "server_config": tool.server_config.model_dump(),  # Pydantic serialization
                }
            )
        return {"server_name": server_name, "tools": tools_data}

    @classmethod
    def _deserialize_plugin_data(cls, plugin_data: Dict) -> type:
        """
        Deserialize plugin data to plugin class.

        Args:
            plugin_data: Serialized plugin data from storage

        Returns:
            type: Dynamically created McpPlugin class
        """
        from sk_agents.tealagents.v1alpha1.config import McpServerConfig

        # Reconstruct McpTool objects
        tools = []
        for tool_data in plugin_data["tools"]:
            server_config = McpServerConfig(**tool_data["server_config"])
            tool = McpTool(
                tool_name=tool_data["tool_name"],
                description=tool_data["description"],
                input_schema=tool_data["input_schema"],
                output_schema=tool_data["output_schema"],
                server_config=server_config,
                server_name=tool_data["server_name"],
            )
            tools.append(tool)

        # Create plugin class dynamically
        return cls._create_plugin_class(tools, plugin_data["server_name"])

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
    async def get_plugin_classes_for_session(
        cls, user_id: str, session_id: str, discovery_manager  # McpDiscoveryManager
    ) -> Dict[str, type]:
        """
        Load plugin classes from external storage for this session.

        Args:
            user_id: User ID
            session_id: Session ID
            discovery_manager: Manager for loading discovery state

        Returns:
            Dictionary mapping server_name to plugin class
        """
        # Load state from external storage
        state = await discovery_manager.load_discovery(user_id, session_id)
        if not state or not state.discovery_completed:
            return {}

        # Deserialize plugin classes
        plugin_classes = {}
        for server_name, plugin_data in state.discovered_servers.items():
            plugin_class = cls._deserialize_plugin_data(plugin_data)
            plugin_classes[server_name] = plugin_class

        logger.debug(
            f"Loaded {len(plugin_classes)} MCP plugin classes for session {session_id}"
        )
        return plugin_classes
