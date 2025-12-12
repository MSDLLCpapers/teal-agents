"""
MCP Plugin Registry - Discovers and stores MCP tools at session start.

This registry discovers MCP tools and stores them in external state.
At request time, tools are loaded from state and used to instantiate
McpPlugin directly in kernel_builder.
"""

import logging
from contextlib import AsyncExitStack
from datetime import datetime, timezone
from typing import Any, Dict, List

from sk_agents.mcp_client import (
    McpPlugin,
    McpTool,
    apply_trust_level_governance,
    create_mcp_session_with_retry,
    map_mcp_annotations_to_governance,
    resolve_server_auth_headers,
)
from sk_agents.plugin_catalog.models import Governance, Oauth2PluginAuth, PluginTool
from sk_agents.plugin_catalog.plugin_catalog_factory import PluginCatalogFactory
from sk_agents.tealagents.v1alpha1.config import GovernanceOverride, McpServerConfig

logger = logging.getLogger(__name__)


class McpPluginRegistry:
    """
    Registry for MCP tools with per-session isolation.

    At session start, this registry:
    1. Connects to MCP servers temporarily
    2. Discovers available tools
    3. Registers tools in catalog for governance/HITL
    4. Serializes tool data to external storage (via McpStateManager)

    At request time:
    - Tools are loaded from storage via get_tools_for_session()
    - kernel_builder instantiates McpPlugin directly with these tools

    This ensures proper multi-tenant isolation and horizontal scalability.
    Tool state is stored externally (Redis/InMemory) instead of class variables.
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
        discovery_manager,  # McpStateManager
        app_config,
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
                plugin_data, discovered_session_id = await cls._discover_server(
                    server_config, user_id, session_id, discovery_manager, app_config
                )

                # Preserve any existing session bucket
                existing_entry = state.discovered_servers.get(server_config.name, {})
                session_bucket = existing_entry.get("session") or {}

                # Always persist freshly discovered plugin data
                state.discovered_servers[server_config.name] = {
                    "plugin_data": plugin_data,
                    **({"session": session_bucket} if session_bucket else {}),
                }
                await discovery_manager.update_discovery(state)

                # If discovery yielded a session id, persist via state manager API
                if discovered_session_id:
                    try:
                        await discovery_manager.store_mcp_session(
                            user_id,
                            session_id,
                            server_config.name,
                            discovered_session_id,
                        )
                        await discovery_manager.update_session_last_used(
                            user_id, session_id, server_config.name
                        )
                    except Exception as err:
                        logger.warning(
                            f"Failed to persist MCP session for {server_config.name}: {err}"
                        )

            except AuthRequiredError as e:
                # Auth error - collect and surface to user
                logger.warning(f"Auth required for MCP server {server_config.name} (session: {session_id})")
                auth_errors.append(e)
            except Exception as e:
                # Other errors - log and continue with remaining servers
                # Extract underlying exception from TaskGroup if needed
                import traceback
                error_details = "".join(traceback.format_exception(type(e), e, e.__traceback__))

                # If it's a TaskGroup exception, try to extract the underlying exception
                underlying_error = str(e)
                if hasattr(e, '__cause__') and e.__cause__:
                    underlying_error = f"{e} (caused by: {e.__cause__})"
                elif hasattr(e, 'exceptions'):
                    # ExceptionGroup-style
                    underlying_error = f"{e} (sub-exceptions: {e.exceptions})"

                logger.error(
                    f"Failed to discover MCP server {server_config.name} for session {session_id}:\n"
                    f"Error: {underlying_error}\n"
                    f"Full traceback:\n{error_details}"
                )
                
                # Capture failure in state
                state.failed_servers[server_config.name] = underlying_error
                try:
                    await discovery_manager.update_discovery(state)
                except Exception as update_err:
                    logger.error(f"Failed to persist discovery error for {server_config.name}: {update_err}")
                    
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
    async def _discover_server(
        cls,
        server_config: McpServerConfig,
        user_id: str,
        session_id: str,
        discovery_manager,
        app_config,
    ) -> tuple[Dict, str | None]:
        """
        Discover tools from a single MCP server.

        Returns:
            Tuple: (Serialized plugin data, optional mcp_session_id)
        """
        logger.info(f"Discovering tools from MCP server: {server_config.name}")

        # Pre-flight auth validation using unified resolver (handles refresh/audience)
        try:
            await resolve_server_auth_headers(
                server_config,
                user_id=user_id,
                app_config=app_config,
            )
            logger.info(f"Auth verified for {server_config.name}, proceeding with discovery")
        except AuthRequiredError:
            raise
        except Exception as e:
            logger.error(f"Auth resolution failed for {server_config.name}: {e}")
            raise

        # Temporary connection for discovery
        async with AsyncExitStack() as stack:
            stored_session_id = None
            if discovery_manager:
                try:
                    stored_session_id = await discovery_manager.get_mcp_session(
                        user_id, session_id, server_config.name
                    )
                except Exception:
                    logger.debug("Unable to fetch stored MCP session id for discovery")

            # Create temp connection (reuse session id if available)
            session, get_session_id = await create_mcp_session_with_retry(
                server_config,
                stack,
                user_id,
                mcp_session_id=stored_session_id,
                on_stale_session=(
                    lambda sid: discovery_manager.clear_mcp_session(
                        user_id, session_id, server_config.name, expected_session_id=sid
                    )
                    if discovery_manager
                    else None
                ),
            )

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

            session_identifier = get_session_id() if get_session_id else None

            logger.info(f"Discovered {len(mcp_tools)} tools from {server_config.name}")
            # Connection auto-closes when exiting context

            return plugin_data, session_identifier

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

            # Map MCP annotations to governance.
            # Newer MCP SDKs return a ToolAnnotations object without dict-like access.
            annotations_obj = getattr(tool_info, "annotations", None)
            if annotations_obj is None:
                annotations = {}
            elif hasattr(annotations_obj, "model_dump"):
                annotations = annotations_obj.model_dump() or {}
            elif isinstance(annotations_obj, dict):
                annotations = annotations_obj
            else:
                # Best-effort fallback for unknown types
                annotations = {}

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

        def _sanitize_server_config(server_config):
            """Drop secrets before persisting discovery state."""
            cfg = server_config.model_dump()

            # Remove confidential OAuth client secret
            cfg.pop("oauth_client_secret", None)

            # Strip Authorization headers to avoid token leakage
            headers = cfg.get("headers") or {}
            cfg["headers"] = {
                k: v for k, v in headers.items() if k.lower() != "authorization"
            }

            # Drop env entries that look sensitive (best‑effort)
            env = cfg.get("env")
            if isinstance(env, dict):
                cfg["env"] = {
                    k: v
                    for k, v in env.items()
                    if not any(s in k.lower() for s in ["secret", "token", "key", "password"])
                }

            return cfg

        tools_data = []
        for tool in tools:
            tools_data.append(
                {
                    "tool_name": tool.tool_name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "output_schema": tool.output_schema,
                    "server_name": tool.server_name,
                    "server_config": _sanitize_server_config(tool.server_config),
                }
            )
        return {"server_name": server_name, "tools": tools_data}

    @classmethod
    def _deserialize_tools(cls, plugin_data: Dict) -> List[McpTool]:
        """
        Deserialize plugin data to McpTool list.

        Args:
            plugin_data: Serialized plugin data from storage

        Returns:
            List of McpTool objects
        """
        from sk_agents.tealagents.v1alpha1.config import McpServerConfig

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

        return tools

    @classmethod
    async def get_tools_for_session(
        cls, user_id: str, session_id: str, discovery_manager  # McpStateManager
    ) -> Dict[str, List[McpTool]]:
        """
        Load MCP tools from external storage for this session.

        Args:
            user_id: User ID
            session_id: Session ID
            discovery_manager: Manager for loading discovery state

        Returns:
            Dictionary mapping server_name to list of McpTool objects
        """
        # Load state from external storage
        state = await discovery_manager.load_discovery(user_id, session_id)
        if not state or not state.discovery_completed:
            return {}

        # Deserialize tools for each server
        server_tools = {}
        for server_name, entry in state.discovered_servers.items():
            plugin_blob = entry.get("plugin_data") if isinstance(entry, dict) else None
            plugin_data = plugin_blob if plugin_blob else entry  # fallback to legacy shape
            tools = cls._deserialize_tools(plugin_data)
            server_tools[server_name] = tools

        logger.debug(
            f"Loaded tools for {len(server_tools)} MCP servers for session {session_id}"
        )
        return server_tools
