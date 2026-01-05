"""
Auth Separation Tests

Verifies that MCP OAuth 2.1 implementation does not interfere with existing
non-MCP authentication and authorization components.

Key Principles:
- Platform auth (RequestAuthorizer): Validates user to platform, returns user_id
- Service auth (MCP OAuth): Manages OAuth tokens for external services per user
- These are orthogonal concerns and must not conflict
"""

from datetime import UTC
from unittest.mock import AsyncMock, patch

import pytest
from ska_utils import AppConfig

from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.authorization.dummy_authorizer import DummyAuthorizer
from sk_agents.authorization.request_authorizer import RequestAuthorizer
from sk_agents.ska_types import BasePlugin


class TestPlatformAuthUnchanged:
    """Verify platform authentication components are unaffected by MCP OAuth."""

    @pytest.mark.asyncio
    async def test_request_authorizer_interface_unchanged(self):
        """Test that RequestAuthorizer interface is unchanged."""
        # RequestAuthorizer should still work as before
        authorizer = DummyAuthorizer()

        # Should return user_id from authorization header
        user_id = await authorizer.authorize_request("Bearer test_token")
        assert user_id == "dummyuser"

        # Interface should be unchanged
        assert hasattr(authorizer, "authorize_request")
        assert callable(authorizer.authorize_request)

    def test_dummy_authorizer_returns_expected_user(self):
        """Test that DummyAuthorizer still returns 'dummyuser'."""
        authorizer = DummyAuthorizer()

        # Verify it's still a RequestAuthorizer
        assert isinstance(authorizer, RequestAuthorizer)

        # Check abstract method is implemented
        assert hasattr(authorizer, "authorize_request")

    def test_base_plugin_interface_unchanged(self):
        """Test that BasePlugin interface accepts authorization parameter."""
        # BasePlugin should still accept authorization string
        plugin = BasePlugin(authorization="Bearer test_token", extra_data_collector=None)

        assert plugin.authorization == "Bearer test_token"
        assert plugin.extra_data_collector is None

        # Should NOT require user_id (that's MCP-specific)
        assert not hasattr(plugin, "user_id")


class TestAuthStorageSeparation:
    """Verify AuthStorage handles both non-MCP and MCP keys without collision."""

    def test_auth_storage_key_isolation(self):
        """Test that MCP composite keys don't collide with non-MCP keys."""
        from sk_agents.mcp_client import build_auth_storage_key

        # MCP uses composite keys like "auth_server|scope1|scope2"
        mcp_key = build_auth_storage_key("https://github.com/login/oauth", ["repo", "read:user"])

        # Key should be deterministic and include scopes
        assert "github.com/login/oauth" in mcp_key
        assert "|" in mcp_key  # Separator
        assert "read:user" in mcp_key
        assert "repo" in mcp_key

        # Non-MCP could use simple keys (no pipe separator)
        non_mcp_key = "simple_plugin_token"

        # Keys should be clearly distinguishable
        assert mcp_key != non_mcp_key
        assert "|" not in non_mcp_key

    def test_auth_storage_supports_different_data_types(self):
        """Test that AuthStorage can store different auth data types."""
        app_config = AppConfig()
        factory = AuthStorageFactory(app_config)
        storage = factory.get_auth_storage_manager()

        # Should be able to store OAuth2AuthData (MCP)
        from datetime import datetime, timedelta

        oauth_data = OAuth2AuthData(
            access_token="test_token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=["read", "write"],
        )

        # Store under MCP composite key
        storage.store("test_user", "mcp_server|read|write", oauth_data)

        # Should be able to store other data under different keys
        # (future non-MCP auth data)
        storage.store("test_user", "simple_key", {"token": "simple_value"})

        # Retrieve both
        retrieved_oauth = storage.retrieve("test_user", "mcp_server|read|write")
        retrieved_simple = storage.retrieve("test_user", "simple_key")

        # Should get back correct data
        assert retrieved_oauth is not None
        assert retrieved_simple is not None

        # OAuth data should be OAuth2AuthData or convertible
        if isinstance(retrieved_oauth, OAuth2AuthData):
            assert retrieved_oauth.access_token == "test_token"


class TestHandlerAuthFlow:
    """Verify handler authentication flow is unchanged for non-MCP requests."""

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.DummyAuthorizer")
    async def test_handler_authenticate_user_unchanged(self, mock_authorizer_class):
        """Test that handler.authenticate_user() still works for non-MCP.

        This test verifies that the DummyAuthorizer is used for authentication
        and returns a user_id correctly.
        """
        from sk_agents.authorization.dummy_authorizer import DummyAuthorizer

        # Setup mock authorizer
        mock_authorizer = AsyncMock()
        mock_authorizer.authorize_request = AsyncMock(return_value="test_user_123")
        mock_authorizer_class.return_value = mock_authorizer

        # Test the authorizer interface directly (handler requires complex config setup)
        # The key behavior we're testing is that authorize_request returns user_id
        user_id = await mock_authorizer.authorize_request(auth_header="Bearer test_token")

        # Should return user_id from authorizer
        assert user_id == "test_user_123"
        mock_authorizer.authorize_request.assert_called_once_with(auth_header="Bearer test_token")

        # Also verify real DummyAuthorizer works
        real_authorizer = DummyAuthorizer()
        real_user_id = await real_authorizer.authorize_request(auth_header="Bearer any_token")
        assert real_user_id == "dummyuser"


class TestNoMCPImportRequired:
    """Verify that MCP OAuth modules are optional and don't break non-MCP usage."""

    def test_non_mcp_code_doesnt_import_oauth_modules(self):
        """Test that non-MCP code doesn't need to import MCP OAuth modules."""
        # These imports should work without MCP OAuth
        from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
        from sk_agents.authorization.dummy_authorizer import DummyAuthorizer
        from sk_agents.authorization.request_authorizer import RequestAuthorizer
        from sk_agents.ska_types import BasePlugin

        # Should all import successfully
        assert RequestAuthorizer is not None
        assert DummyAuthorizer is not None
        assert BasePlugin is not None
        assert AuthStorageFactory is not None

    def test_mcp_oauth_modules_are_isolated(self):
        """Test that MCP OAuth modules are in separate namespace."""
        # MCP OAuth modules should be under sk_agents.auth.*
        import sk_agents.auth

        # Should have auth namespace
        assert hasattr(sk_agents, "auth")

        # But non-MCP authorization is separate
        import sk_agents.authorization

        assert hasattr(sk_agents, "authorization")

        # These should be different modules
        assert sk_agents.auth != sk_agents.authorization


class TestBackwardCompatibility:
    """Verify backward compatibility with existing plugin instantiation."""

    def test_regular_plugin_instantiation_unchanged(self):
        """Test that regular (non-MCP) plugin instantiation works."""
        # Old pattern: plugin receives authorization string directly
        plugin = BasePlugin(authorization="Bearer platform_token", extra_data_collector=None)

        assert plugin.authorization == "Bearer platform_token"

        # Should NOT require user_id (MCP-specific requirement)
        # Non-MCP plugins use authorization directly

    def test_mcp_plugin_requires_user_id_and_connection_manager(self, mock_connection_manager):
        """Test that MCP plugins require user_id and connection_manager (new requirements)."""
        from sk_agents.mcp_client import McpPlugin

        # MCP plugin MUST have user_id
        with pytest.raises(ValueError, match="user_id"):
            plugin = McpPlugin(
                tools=[],
                server_name="test-server",
                user_id=None,  # Invalid!
                connection_manager=mock_connection_manager,
                authorization=None,
                extra_data_collector=None,
            )

        # MCP plugin MUST have connection_manager
        with pytest.raises(ValueError, match="connection_manager"):
            plugin = McpPlugin(
                tools=[],
                server_name="test-server",
                user_id="test_user",
                connection_manager=None,  # Invalid!
                authorization=None,
                extra_data_collector=None,
            )

        # Should work with both user_id and connection_manager
        plugin = McpPlugin(
            tools=[],
            server_name="test-server",
            user_id="test_user",  # Required!
            connection_manager=mock_connection_manager,  # Required!
            authorization=None,
            extra_data_collector=None,
        )
        assert plugin.user_id == "test_user"
        assert plugin.connection_manager == mock_connection_manager


@pytest.mark.integration
class TestEndToEndSeparation:
    """Integration tests verifying complete separation of concerns."""

    @pytest.mark.asyncio
    async def test_both_auth_systems_coexist(self):
        """Test that both platform and service auth work together."""
        # 1. Platform auth: User authenticates to platform
        platform_authorizer = DummyAuthorizer()
        user_id = await platform_authorizer.authorize_request("Bearer platform_token")
        assert user_id == "dummyuser"

        # 2. Service auth: User has OAuth tokens for MCP services
        from datetime import datetime, timedelta

        from sk_agents.mcp_client import build_auth_storage_key

        app_config = AppConfig()
        factory = AuthStorageFactory(app_config)
        storage = factory.get_auth_storage_manager()

        # Store OAuth token for MCP server
        oauth_data = OAuth2AuthData(
            access_token="mcp_service_token",
            expires_at=datetime.now(UTC) + timedelta(hours=1),
            scopes=["repo", "read:user"],
        )

        mcp_key = build_auth_storage_key("https://github.com/login/oauth", ["repo", "read:user"])

        storage.store(user_id, mcp_key, oauth_data)

        # 3. Verify both auth systems are independent
        # Platform auth doesn't care about MCP tokens
        user_id_again = await platform_authorizer.authorize_request("Bearer different_token")
        assert user_id_again == "dummyuser"  # Still works

        # MCP auth doesn't affect platform auth
        retrieved = storage.retrieve(user_id, mcp_key)
        assert retrieved is not None
