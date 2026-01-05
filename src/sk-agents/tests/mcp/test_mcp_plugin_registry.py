"""
Integration tests for MCP Plugin Registry.

Tests discovery, tool deserialization, and catalog registration.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from sk_agents.mcp_client import McpTool
from sk_agents.mcp_discovery.mcp_discovery_manager import McpState
from sk_agents.mcp_plugin_registry import McpPluginRegistry

# ============================================================================
# Fixtures for Discovery Manager
# ============================================================================


@pytest.fixture
def mock_discovery_manager():
    """Create a mock discovery manager (McpStateManager) for testing."""
    manager = MagicMock()
    manager.load_discovery = AsyncMock(return_value=None)
    manager.create_discovery = AsyncMock()
    manager.update_discovery = AsyncMock()
    manager.mark_completed = AsyncMock()
    manager.is_completed = AsyncMock(return_value=False)
    manager.store_mcp_session = AsyncMock()
    manager.get_mcp_session = AsyncMock(return_value=None)
    manager.update_session_last_used = AsyncMock()
    manager.clear_mcp_session = AsyncMock()
    return manager


@pytest.fixture
def mock_discovery_state_with_tools(http_mcp_config):
    """Create a mock McpState with discovered tools."""
    return McpState(
        user_id="test_user",
        session_id="test_session",
        discovered_servers={
            "test-http": {
                "plugin_data": {
                    "server_name": "test-http",
                    "tools": [
                        {
                            "tool_name": "test_tool",
                            "description": "A test tool for MCP",
                            "input_schema": {
                                "type": "object",
                                "properties": {"param1": {"type": "string"}},
                                "required": ["param1"],
                            },
                            "output_schema": None,
                            "server_name": "test-http",
                            "server_config": http_mcp_config.model_dump(),
                        }
                    ],
                }
            }
        },
        discovery_completed=True,
    )


# ============================================================================
# Test Tool Deserialization
# ============================================================================


class TestToolDeserialization:
    """Test deserializing tools from state storage."""

    def test_deserialize_tools_single_tool(self, http_mcp_config):
        """Test deserializing a single tool from plugin data."""
        plugin_data = {
            "server_name": "test-http",
            "tools": [
                {
                    "tool_name": "test_tool",
                    "description": "A test tool",
                    "input_schema": {"type": "object", "properties": {}},
                    "output_schema": None,
                    "server_name": "test-http",
                    "server_config": http_mcp_config.model_dump(),
                }
            ],
        }

        tools = McpPluginRegistry._deserialize_tools(plugin_data)

        assert len(tools) == 1
        assert isinstance(tools[0], McpTool)
        assert tools[0].tool_name == "test_tool"
        assert tools[0].description == "A test tool"
        assert tools[0].server_name == "test-http"

    def test_deserialize_tools_multiple_tools(self, http_mcp_config):
        """Test deserializing multiple tools from plugin data."""
        plugin_data = {
            "server_name": "test-http",
            "tools": [
                {
                    "tool_name": "tool_one",
                    "description": "First tool",
                    "input_schema": {},
                    "output_schema": None,
                    "server_name": "test-http",
                    "server_config": http_mcp_config.model_dump(),
                },
                {
                    "tool_name": "tool_two",
                    "description": "Second tool",
                    "input_schema": {},
                    "output_schema": None,
                    "server_name": "test-http",
                    "server_config": http_mcp_config.model_dump(),
                },
            ],
        }

        tools = McpPluginRegistry._deserialize_tools(plugin_data)

        assert len(tools) == 2
        assert tools[0].tool_name == "tool_one"
        assert tools[1].tool_name == "tool_two"

    def test_deserialize_tools_preserves_schema(self, http_mcp_config):
        """Test that input/output schemas are preserved."""
        input_schema = {
            "type": "object",
            "properties": {"name": {"type": "string"}, "count": {"type": "integer"}},
            "required": ["name"],
        }
        output_schema = {"type": "string"}

        plugin_data = {
            "server_name": "test-http",
            "tools": [
                {
                    "tool_name": "schema_tool",
                    "description": "Tool with schemas",
                    "input_schema": input_schema,
                    "output_schema": output_schema,
                    "server_name": "test-http",
                    "server_config": http_mcp_config.model_dump(),
                }
            ],
        }

        tools = McpPluginRegistry._deserialize_tools(plugin_data)

        assert tools[0].input_schema == input_schema
        assert tools[0].output_schema == output_schema


# ============================================================================
# Test get_tools_for_session
# ============================================================================


class TestGetToolsForSession:
    """Test loading tools from external state storage."""

    @pytest.mark.asyncio
    async def test_get_tools_returns_empty_when_no_state(self, mock_discovery_manager):
        """Test that empty dict is returned when no state exists."""
        mock_discovery_manager.load_discovery.return_value = None

        tools = await McpPluginRegistry.get_tools_for_session(
            user_id="test_user", session_id="test_session", discovery_manager=mock_discovery_manager
        )

        assert tools == {}

    @pytest.mark.asyncio
    async def test_get_tools_returns_empty_when_discovery_incomplete(self, mock_discovery_manager):
        """Test that empty dict is returned when discovery is not completed."""
        incomplete_state = McpState(
            user_id="test_user",
            session_id="test_session",
            discovered_servers={},
            discovery_completed=False,
        )
        mock_discovery_manager.load_discovery.return_value = incomplete_state

        tools = await McpPluginRegistry.get_tools_for_session(
            user_id="test_user", session_id="test_session", discovery_manager=mock_discovery_manager
        )

        assert tools == {}

    @pytest.mark.asyncio
    async def test_get_tools_returns_tools_when_discovery_complete(
        self, mock_discovery_manager, mock_discovery_state_with_tools
    ):
        """Test that tools are returned when discovery is complete."""
        mock_discovery_manager.load_discovery.return_value = mock_discovery_state_with_tools

        server_tools = await McpPluginRegistry.get_tools_for_session(
            user_id="test_user", session_id="test_session", discovery_manager=mock_discovery_manager
        )

        assert "test-http" in server_tools
        tools = server_tools["test-http"]
        assert len(tools) == 1
        assert isinstance(tools[0], McpTool)
        assert tools[0].tool_name == "test_tool"

    @pytest.mark.asyncio
    async def test_get_tools_for_multiple_servers(
        self, mock_discovery_manager, http_mcp_config, stdio_mcp_config
    ):
        """Test loading tools from multiple MCP servers."""
        multi_server_state = McpState(
            user_id="test_user",
            session_id="test_session",
            discovered_servers={
                "test-http": {
                    "plugin_data": {
                        "server_name": "test-http",
                        "tools": [
                            {
                                "tool_name": "http_tool",
                                "description": "HTTP tool",
                                "input_schema": {},
                                "output_schema": None,
                                "server_name": "test-http",
                                "server_config": http_mcp_config.model_dump(),
                            }
                        ],
                    }
                },
                "test-stdio": {
                    "plugin_data": {
                        "server_name": "test-stdio",
                        "tools": [
                            {
                                "tool_name": "stdio_tool",
                                "description": "Stdio tool",
                                "input_schema": {},
                                "output_schema": None,
                                "server_name": "test-stdio",
                                "server_config": stdio_mcp_config.model_dump(),
                            }
                        ],
                    }
                },
            },
            discovery_completed=True,
        )
        mock_discovery_manager.load_discovery.return_value = multi_server_state

        server_tools = await McpPluginRegistry.get_tools_for_session(
            user_id="test_user", session_id="test_session", discovery_manager=mock_discovery_manager
        )

        assert len(server_tools) == 2
        assert "test-http" in server_tools
        assert "test-stdio" in server_tools
        assert server_tools["test-http"][0].tool_name == "http_tool"
        assert server_tools["test-stdio"][0].tool_name == "stdio_tool"


# ============================================================================
# Test Tool Catalog Registration
# ============================================================================


class TestCatalogRegistration:
    """Test MCP tool registration in plugin catalog."""

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.resolve_server_auth_headers")
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session_with_retry")
    async def test_tools_registered_in_catalog(
        self,
        mock_create_session,
        mock_catalog_factory_class,
        mock_resolve_auth,
        mock_discovery_manager,
        http_mcp_config,
        mock_mcp_tool,
    ):
        """Test that discovered tools are registered in catalog."""
        # Setup mock auth
        mock_resolve_auth.return_value = {"Authorization": "Bearer token"}

        # Setup mock catalog
        mock_catalog = MagicMock()
        mock_catalog.register_dynamic_tool = Mock()
        mock_factory = MagicMock()
        mock_factory.get_catalog.return_value = mock_catalog
        mock_catalog_factory_class.return_value = mock_factory

        # Setup mock session
        mock_session = AsyncMock()
        tools_result = MagicMock()
        tools_result.tools = [mock_mcp_tool]
        mock_session.list_tools = AsyncMock(return_value=tools_result)
        mock_create_session.return_value = (mock_session, lambda: "session-123")

        # Setup discovery manager with initial state
        initial_state = McpState(
            user_id="test_user",
            session_id="test_session",
            discovered_servers={},
            discovery_completed=False,
        )
        mock_discovery_manager.load_discovery.return_value = initial_state

        # Discover
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="test_user",
            session_id="test_session",
            discovery_manager=mock_discovery_manager,
            app_config=MagicMock(),
        )

        # Verify catalog registration
        mock_catalog.register_dynamic_tool.assert_called_once()
        call_args = mock_catalog.register_dynamic_tool.call_args

        # Check tool registration
        registered_tool = call_args[0][0]  # First positional arg
        assert registered_tool.tool_id == "mcp_test-http_test_tool"
        assert registered_tool.name == "test_tool"


# ============================================================================
# Test Session Isolation
# ============================================================================


class TestSessionIsolation:
    """Test that tools are isolated per (user_id, session_id)."""

    @pytest.mark.asyncio
    async def test_different_sessions_get_different_tools(
        self, mock_discovery_manager, http_mcp_config
    ):
        """Test that different sessions load their own tools."""
        # Session A has tool_a
        state_a = McpState(
            user_id="user_a",
            session_id="session_a",
            discovered_servers={
                "server": {
                    "plugin_data": {
                        "server_name": "server",
                        "tools": [
                            {
                                "tool_name": "tool_a",
                                "description": "Tool A",
                                "input_schema": {},
                                "output_schema": None,
                                "server_name": "server",
                                "server_config": http_mcp_config.model_dump(),
                            }
                        ],
                    }
                }
            },
            discovery_completed=True,
        )

        # Session B has tool_b
        state_b = McpState(
            user_id="user_b",
            session_id="session_b",
            discovered_servers={
                "server": {
                    "plugin_data": {
                        "server_name": "server",
                        "tools": [
                            {
                                "tool_name": "tool_b",
                                "description": "Tool B",
                                "input_schema": {},
                                "output_schema": None,
                                "server_name": "server",
                                "server_config": http_mcp_config.model_dump(),
                            }
                        ],
                    }
                }
            },
            discovery_completed=True,
        )

        # Load for session A
        mock_discovery_manager.load_discovery.return_value = state_a
        tools_a = await McpPluginRegistry.get_tools_for_session(
            "user_a", "session_a", mock_discovery_manager
        )

        # Load for session B
        mock_discovery_manager.load_discovery.return_value = state_b
        tools_b = await McpPluginRegistry.get_tools_for_session(
            "user_b", "session_b", mock_discovery_manager
        )

        # Verify isolation
        assert tools_a["server"][0].tool_name == "tool_a"
        assert tools_b["server"][0].tool_name == "tool_b"
