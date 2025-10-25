"""
Integration tests for MCP Plugin Registry.

Tests discovery, materialization, and catalog registration without real MCP servers.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from mcp.types import Tool

from sk_agents.mcp_plugin_registry import McpPluginRegistry
from sk_agents.plugin_catalog.models import Governance
from sk_agents.tealagents.v1alpha1.config import McpServerConfig


# ============================================================================
# Test Registry Discovery and Materialization
# ============================================================================

class TestRegistryDiscovery:
    """Test MCP server discovery and plugin class creation."""

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_discover_single_server(self, mock_create_session, http_mcp_config, mock_mcp_session):
        """Test discovering tools from a single MCP server."""
        # Setup mock session
        mock_create_session.return_value = mock_mcp_session

        # Clear registry
        McpPluginRegistry.clear()

        # Discover
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="test_user"
        )

        # Verify plugin class was created
        plugin_class = McpPluginRegistry.get_plugin_class("test-http")
        assert plugin_class is not None
        assert plugin_class.__name__ == "McpPlugin_test-http"

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_discover_multiple_servers(self, mock_create_session, http_mcp_config, stdio_mcp_config, mock_mcp_session):
        """Test discovering tools from multiple servers."""
        mock_create_session.return_value = mock_mcp_session

        McpPluginRegistry.clear()

        # Discover multiple servers
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config, stdio_mcp_config],
            user_id="test_user"
        )

        # Verify both plugin classes created
        all_classes = McpPluginRegistry.get_all_plugin_classes()
        assert len(all_classes) == 2
        assert "test-http" in all_classes
        assert "test-stdio" in all_classes

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_discovery_failure_continues(self, mock_create_session, http_mcp_config, stdio_mcp_config):
        """Test that discovery continues even if one server fails."""
        # First server fails, second succeeds
        mock_failing_session = AsyncMock()
        mock_failing_session.list_tools = AsyncMock(side_effect=Exception("Connection failed"))

        mock_success_session = AsyncMock()
        success_tool = MagicMock(spec=Tool)
        success_tool.name = "success_tool"
        success_tool.description = "A successful tool"
        success_tool.inputSchema = {}
        success_tool.annotations = {}
        tools_result = MagicMock()
        tools_result.tools = [success_tool]
        mock_success_session.list_tools = AsyncMock(return_value=tools_result)

        # Return different sessions for different servers
        mock_create_session.side_effect = [mock_failing_session, mock_success_session]

        McpPluginRegistry.clear()

        # Should not raise despite first server failing
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config, stdio_mcp_config],
            user_id="test_user"
        )

        # Only successful server should be registered
        all_classes = McpPluginRegistry.get_all_plugin_classes()
        assert len(all_classes) == 1
        assert "test-stdio" in all_classes


# ============================================================================
# Test Plugin Class Instantiation
# ============================================================================

class TestPluginInstantiation:
    """Test instantiating plugin classes with user_id."""

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_instantiate_plugin_with_user_id(self, mock_create_session, http_mcp_config, mock_mcp_session):
        """Test that plugin class can be instantiated with user_id."""
        mock_create_session.return_value = mock_mcp_session

        McpPluginRegistry.clear()

        # Discover
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="discovery_user"
        )

        # Get class and instantiate with different user
        plugin_class = McpPluginRegistry.get_plugin_class("test-http")
        plugin_instance = plugin_class(
            user_id="request_user_123",
            authorization="Bearer token",
            extra_data_collector=None
        )

        # Verify instance properties
        assert plugin_instance.user_id == "request_user_123"
        assert plugin_instance.server_name == "test-http"
        assert plugin_instance.authorization == "Bearer token"

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_instantiate_multiple_instances_different_users(self, mock_create_session, http_mcp_config, mock_mcp_session):
        """Test creating multiple plugin instances for different users."""
        mock_create_session.return_value = mock_mcp_session

        McpPluginRegistry.clear()

        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="discovery_user"
        )

        # Get class
        plugin_class = McpPluginRegistry.get_plugin_class("test-http")

        # Create instances for different users
        instance1 = plugin_class(user_id="user_1", authorization=None, extra_data_collector=None)
        instance2 = plugin_class(user_id="user_2", authorization=None, extra_data_collector=None)
        instance3 = plugin_class(user_id="user_3", authorization=None, extra_data_collector=None)

        # Verify each has correct user_id
        assert instance1.user_id == "user_1"
        assert instance2.user_id == "user_2"
        assert instance3.user_id == "user_3"

        # Verify all reference same server
        assert instance1.server_name == instance2.server_name == instance3.server_name == "test-http"


# ============================================================================
# Test Tool Catalog Registration
# ============================================================================

class TestCatalogRegistration:
    """Test MCP tool registration in plugin catalog."""

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_tools_registered_in_catalog(self, mock_create_session, mock_catalog_factory_class, http_mcp_config, mock_mcp_tool):
        """Test that discovered tools are registered in catalog."""
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
        mock_create_session.return_value = mock_session

        McpPluginRegistry.clear()

        # Discover
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="test_user"
        )

        # Verify catalog registration
        mock_catalog.register_dynamic_tool.assert_called_once()
        call_args = mock_catalog.register_dynamic_tool.call_args

        # Check tool registration
        registered_tool = call_args[0][0]  # First positional arg
        assert registered_tool.tool_id == "mcp_test-http_test_tool"
        assert registered_tool.name == "test_tool"
        assert registered_tool.description == "A test tool for MCP"

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_governance_applied_to_catalog_tools(self, mock_create_session, mock_catalog_factory_class, mock_destructive_tool):
        """Test that governance is correctly applied when registering in catalog."""
        # Setup mocks
        mock_catalog = MagicMock()
        mock_catalog.register_dynamic_tool = Mock()
        mock_factory = MagicMock()
        mock_factory.get_catalog.return_value = mock_catalog
        mock_catalog_factory_class.return_value = mock_factory

        mock_session = AsyncMock()
        tools_result = MagicMock()
        tools_result.tools = [mock_destructive_tool]
        mock_session.list_tools = AsyncMock(return_value=tools_result)
        mock_create_session.return_value = mock_session

        # Untrusted server config
        config = McpServerConfig(
            name="untrusted-server",
            transport="http",
            url="https://untrusted.example.com/mcp",
            auth_server="https://untrusted.example.com/oauth",
            scopes=["read"],
            trust_level="untrusted"
        )

        McpPluginRegistry.clear()

        await McpPluginRegistry.discover_and_materialize([config], user_id="test_user")

        # Check governance
        call_args = mock_catalog.register_dynamic_tool.call_args
        registered_tool = call_args[0][0]
        governance = registered_tool.governance

        # Destructive + untrusted = strict governance
        assert governance.requires_hitl is True
        assert governance.cost == "high"

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_governance_overrides_applied(self, mock_create_session, mock_catalog_factory_class, mock_mcp_tool):
        """Test that manual governance overrides from config are applied."""
        # Setup mocks
        mock_catalog = MagicMock()
        mock_catalog.register_dynamic_tool = Mock()
        mock_factory = MagicMock()
        mock_factory.get_catalog.return_value = mock_catalog
        mock_catalog_factory_class.return_value = mock_factory

        mock_session = AsyncMock()
        tools_result = MagicMock()
        tools_result.tools = [mock_mcp_tool]
        mock_session.list_tools = AsyncMock(return_value=tools_result)
        mock_create_session.return_value = mock_session

        # Config with governance overrides
        config = McpServerConfig(
            name="override-server",
            transport="http",
            url="https://example.com/mcp",
            auth_server="https://example.com/oauth",
            scopes=["read"],
            trust_level="trusted",
            tool_governance_overrides={
                "test_tool": {
                    "requires_hitl": False,  # Override to allow auto-execution
                    "cost": "low",
                    "data_sensitivity": "public"
                }
            }
        )

        McpPluginRegistry.clear()

        await McpPluginRegistry.discover_and_materialize([config], user_id="test_user")

        # Check overrides applied
        call_args = mock_catalog.register_dynamic_tool.call_args
        registered_tool = call_args[0][0]
        governance = registered_tool.governance

        assert governance.requires_hitl is False  # Overridden!
        assert governance.cost == "low"
        assert governance.data_sensitivity == "public"

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_oauth_auth_registered_for_http_servers(self, mock_create_session, mock_catalog_factory_class, mock_mcp_tool):
        """Test that OAuth2 auth config is registered for HTTP servers."""
        # Setup mocks
        mock_catalog = MagicMock()
        mock_catalog.register_dynamic_tool = Mock()
        mock_factory = MagicMock()
        mock_factory.get_catalog.return_value = mock_catalog
        mock_catalog_factory_class.return_value = mock_factory

        mock_session = AsyncMock()
        tools_result = MagicMock()
        tools_result.tools = [mock_mcp_tool]
        mock_session.list_tools = AsyncMock(return_value=tools_result)
        mock_create_session.return_value = mock_session

        # HTTP server with OAuth
        config = McpServerConfig(
            name="github",
            transport="http",
            url="https://api.github.com/mcp",
            auth_server="https://github.com/login/oauth",
            scopes=["repo", "read:user"]
        )

        McpPluginRegistry.clear()

        await McpPluginRegistry.discover_and_materialize([config], user_id="test_user")

        # Check auth registered
        call_args = mock_catalog.register_dynamic_tool.call_args
        registered_tool = call_args[0][0]
        auth = registered_tool.auth

        assert auth is not None
        assert auth.auth_server == "https://github.com/login/oauth"
        assert set(auth.scopes) == {"repo", "read:user"}


# ============================================================================
# Test Registry Utilities
# ============================================================================

class TestRegistryUtilities:
    """Test registry helper methods."""

    def test_get_nonexistent_plugin_class(self):
        """Test getting plugin class that doesn't exist."""
        McpPluginRegistry.clear()
        plugin_class = McpPluginRegistry.get_plugin_class("nonexistent-server")
        assert plugin_class is None

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_get_all_plugin_classes(self, mock_create_session, http_mcp_config, stdio_mcp_config, mock_mcp_session):
        """Test getting all registered plugin classes."""
        mock_create_session.return_value = mock_mcp_session

        McpPluginRegistry.clear()

        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config, stdio_mcp_config],
            user_id="test_user"
        )

        all_classes = McpPluginRegistry.get_all_plugin_classes()

        assert len(all_classes) == 2
        assert "test-http" in all_classes
        assert "test-stdio" in all_classes
        assert all(callable(cls) for cls in all_classes.values())

    def test_clear_registry(self):
        """Test clearing the registry."""
        McpPluginRegistry.clear()

        # Manually add a class
        with McpPluginRegistry._lock:
            McpPluginRegistry._plugin_classes["test"] = type("TestPlugin", (), {})

        assert len(McpPluginRegistry.get_all_plugin_classes()) == 1

        # Clear
        McpPluginRegistry.clear()

        assert len(McpPluginRegistry.get_all_plugin_classes()) == 0
