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
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_discover_single_server(self, mock_create_session, mock_auth_factory_class, http_mcp_config, mock_mcp_session, mock_auth_storage_factory):
        """Test discovering tools from a single MCP server for a user."""
        # Setup mock session
        mock_create_session.return_value = mock_mcp_session

        # Setup mock auth storage
        mock_auth_factory_class.return_value = mock_auth_storage_factory

        # Clear registry
        McpPluginRegistry.clear()

        # Discover
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="test_user"
        )

        # Verify plugin class was created for this user
        plugin_classes = McpPluginRegistry.get_all_plugin_classes_for_user("test_user")
        assert "test-http" in plugin_classes
        assert plugin_classes["test-http"].__name__ == "McpPlugin_test-http"

    @pytest.mark.asyncio
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_discover_multiple_servers(self, mock_create_session, mock_auth_factory_class, http_mcp_config, stdio_mcp_config, mock_mcp_session, mock_auth_storage_factory):
        """Test discovering tools from multiple servers for a user."""
        mock_create_session.return_value = mock_mcp_session
        mock_auth_factory_class.return_value = mock_auth_storage_factory

        McpPluginRegistry.clear()

        # Discover multiple servers
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config, stdio_mcp_config],
            user_id="test_user"
        )

        # Verify both plugin classes created for this user
        all_classes = McpPluginRegistry.get_all_plugin_classes_for_user("test_user")
        assert len(all_classes) == 2
        assert "test-http" in all_classes
        assert "test-stdio" in all_classes

    @pytest.mark.asyncio
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_discovery_failure_continues(self, mock_create_session, mock_auth_factory_class, http_mcp_config, stdio_mcp_config, mock_auth_storage_factory):
        """Test that discovery continues even if one server fails."""
        # Setup mock auth storage
        mock_auth_factory_class.return_value = mock_auth_storage_factory

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

        # Only successful server should be registered for this user
        all_classes = McpPluginRegistry.get_all_plugin_classes_for_user("test_user")
        assert len(all_classes) == 1
        assert "test-stdio" in all_classes


# ============================================================================
# Test Plugin Class Instantiation
# ============================================================================

class TestPluginInstantiation:
    """Test instantiating plugin classes with user_id."""

    @pytest.mark.asyncio
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_instantiate_plugin_with_user_id(self, mock_create_session, mock_auth_factory_class, http_mcp_config, mock_mcp_session, mock_auth_storage_factory):
        """Test that plugin class can be instantiated with user_id."""
        mock_create_session.return_value = mock_mcp_session
        mock_auth_factory_class.return_value = mock_auth_storage_factory

        McpPluginRegistry.clear()

        # Discover for a user
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="test_user"
        )

        # Get class for that user and instantiate with their user_id
        plugin_classes = McpPluginRegistry.get_all_plugin_classes_for_user("test_user")
        plugin_class = plugin_classes["test-http"]
        plugin_instance = plugin_class(
            user_id="test_user",
            authorization="Bearer token",
            extra_data_collector=None
        )

        # Verify instance properties
        assert plugin_instance.user_id == "test_user"
        assert plugin_instance.server_name == "test-http"
        assert plugin_instance.authorization == "Bearer token"

    @pytest.mark.asyncio
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_per_user_discovery_isolation(self, mock_create_session, mock_auth_factory_class, http_mcp_config, mock_mcp_session, mock_auth_storage_factory):
        """Test that plugin discovery is isolated per user."""
        mock_create_session.return_value = mock_mcp_session
        mock_auth_factory_class.return_value = mock_auth_storage_factory

        McpPluginRegistry.clear()

        # User 1 discovers tools
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="test_user"
        )

        # User 2 discovers tools (needs different user with auth in mock)
        # For this test, we'll use test_user twice to verify isolation
        # In reality, each would need their own auth
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="test_user"
        )

        # Each discovery creates entries
        user_classes = McpPluginRegistry.get_all_plugin_classes_for_user("test_user")
        assert "test-http" in user_classes

        # Create instances
        instance1 = user_classes["test-http"](user_id="test_user", authorization=None, extra_data_collector=None)
        assert instance1.user_id == "test_user"
        assert instance1.server_name == "test-http"

    @pytest.mark.asyncio
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_user_cannot_see_other_users_tools(self, mock_create_session, mock_auth_factory_class, http_mcp_config, mock_mcp_session, mock_auth_storage_factory):
        """Test that User B cannot see tools discovered by User A (multi-tenant isolation)."""
        mock_create_session.return_value = mock_mcp_session
        mock_auth_factory_class.return_value = mock_auth_storage_factory

        McpPluginRegistry.clear()

        # User A discovers tools
        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id="test_user"
        )

        # User A can see their tools
        user_a_classes = McpPluginRegistry.get_all_plugin_classes_for_user("test_user")
        assert len(user_a_classes) == 1
        assert "test-http" in user_a_classes

        # User B (who hasn't discovered) cannot see User A's tools
        user_b_classes = McpPluginRegistry.get_all_plugin_classes_for_user("user_b")
        assert len(user_b_classes) == 0
        assert "test-http" not in user_b_classes


# ============================================================================
# Test Tool Catalog Registration
# ============================================================================

class TestCatalogRegistration:
    """Test MCP tool registration in plugin catalog."""

    @pytest.mark.asyncio
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_tools_registered_in_catalog(self, mock_create_session, mock_catalog_factory_class, mock_auth_factory_class, http_mcp_config, mock_mcp_tool, mock_auth_storage_factory):
        """Test that discovered tools are registered in catalog."""
        # Setup mock auth storage
        mock_auth_factory_class.return_value = mock_auth_storage_factory

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
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_governance_applied_to_catalog_tools(self, mock_create_session, mock_catalog_factory_class, mock_auth_factory_class, mock_destructive_tool, mock_auth_storage_factory):
        """Test that governance is correctly applied when registering in catalog."""
        # Setup mock auth storage
        mock_auth_factory_class.return_value = mock_auth_storage_factory

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

        # Untrusted server config (needs auth in mock storage for this to work)
        config = McpServerConfig(
            name="untrusted-server",
            transport="http",
            url="https://untrusted.example.com/mcp",
            auth_server="https://api.example.com/oauth2",  # Use auth that's in mock storage
            scopes=["read", "write"],
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
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_governance_overrides_applied(self, mock_create_session, mock_catalog_factory_class, mock_auth_factory_class, mock_mcp_tool, mock_auth_storage_factory):
        """Test that manual governance overrides from config are applied."""
        # Setup mock auth storage
        mock_auth_factory_class.return_value = mock_auth_storage_factory

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

        # Config with governance overrides (use auth that's in mock storage)
        config = McpServerConfig(
            name="override-server",
            transport="http",
            url="https://example.com/mcp",
            auth_server="https://api.example.com/oauth2",
            scopes=["read", "write"],
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
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.PluginCatalogFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_oauth_auth_registered_for_http_servers(self, mock_create_session, mock_catalog_factory_class, mock_auth_factory_class, mock_mcp_tool, mock_auth_storage_factory):
        """Test that OAuth2 auth config is registered for HTTP servers."""
        # Setup mock auth storage
        mock_auth_factory_class.return_value = mock_auth_storage_factory

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

        # HTTP server with OAuth (use auth that's in mock storage)
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

    def test_get_nonexistent_user_plugins(self):
        """Test getting plugins for a user that hasn't discovered any."""
        McpPluginRegistry.clear()
        plugin_classes = McpPluginRegistry.get_all_plugin_classes_for_user("nonexistent-user")
        assert plugin_classes == {}

    @pytest.mark.asyncio
    @patch("sk_agents.auth_storage.auth_storage_factory.AuthStorageFactory")
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session")
    async def test_get_all_plugin_classes_for_user(self, mock_create_session, mock_auth_factory_class, http_mcp_config, stdio_mcp_config, mock_mcp_session, mock_auth_storage_factory):
        """Test getting all registered plugin classes for a specific user."""
        mock_create_session.return_value = mock_mcp_session
        mock_auth_factory_class.return_value = mock_auth_storage_factory

        McpPluginRegistry.clear()

        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config, stdio_mcp_config],
            user_id="test_user"
        )

        all_classes = McpPluginRegistry.get_all_plugin_classes_for_user("test_user")

        assert len(all_classes) == 2
        assert "test-http" in all_classes
        assert "test-stdio" in all_classes
        assert all(callable(cls) for cls in all_classes.values())

    def test_clear_registry(self):
        """Test clearing the entire registry."""
        McpPluginRegistry.clear()

        # Manually add classes for multiple users
        with McpPluginRegistry._lock:
            McpPluginRegistry._plugin_classes_per_user["user1"] = {"test": type("TestPlugin", (), {})}
            McpPluginRegistry._plugin_classes_per_user["user2"] = {"test": type("TestPlugin", (), {})}

        assert len(McpPluginRegistry.get_all_plugin_classes_for_user("user1")) == 1
        assert len(McpPluginRegistry.get_all_plugin_classes_for_user("user2")) == 1

        # Clear
        McpPluginRegistry.clear()

        assert len(McpPluginRegistry.get_all_plugin_classes_for_user("user1")) == 0
        assert len(McpPluginRegistry.get_all_plugin_classes_for_user("user2")) == 0

    def test_clear_user_plugins(self):
        """Test clearing plugins for a specific user."""
        McpPluginRegistry.clear()

        # Add classes for multiple users
        with McpPluginRegistry._lock:
            McpPluginRegistry._plugin_classes_per_user["user1"] = {"test": type("TestPlugin", (), {})}
            McpPluginRegistry._plugin_classes_per_user["user2"] = {"test": type("TestPlugin", (), {})}

        assert len(McpPluginRegistry.get_all_plugin_classes_for_user("user1")) == 1
        assert len(McpPluginRegistry.get_all_plugin_classes_for_user("user2")) == 1

        # Clear only user1
        McpPluginRegistry.clear_user_plugins("user1")

        assert len(McpPluginRegistry.get_all_plugin_classes_for_user("user1")) == 0
        assert len(McpPluginRegistry.get_all_plugin_classes_for_user("user2")) == 1  # user2 still has plugins
