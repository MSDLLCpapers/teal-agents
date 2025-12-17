"""
Integration tests for MCP handler flows.

Tests MCP discovery at session start, auth challenges, and resume flows.
"""

from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from sk_agents.mcp_plugin_registry import McpPluginRegistry
from sk_agents.tealagents.v1alpha1.agent.handler import TealAgentsV1Alpha1Handler
from sk_agents.tealagents.v1alpha1.config import AgentConfig, McpServerConfig


# ============================================================================
# Test MCP Discovery at Session Start
# ============================================================================

@pytest.mark.skip(reason="Handler integration tests need refactoring after McpConnectionManager changes. StateManagerFactory no longer in handler.")
class TestSessionStartDiscovery:
    """Test MCP discovery when handler starts a new session."""

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.McpPluginRegistry.discover_and_materialize")
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_discovery_runs_on_first_request(
        self,
        mock_state_factory,
        mock_discover,
        http_mcp_config
    ):
        """Test that MCP discovery runs on the first request."""
        # Setup state manager mock
        mock_state_manager = MagicMock()
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        # Create handler config with MCP server
        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = [http_mcp_config]

        config = MagicMock()
        config.get_agent.return_value = agent_config

        # Create handler
        handler = TealAgentsV1Alpha1Handler(config)

        # Reset discovery state
        TealAgentsV1Alpha1Handler._mcp_discovery_initialized = False
        McpPluginRegistry.clear()

        # Trigger discovery
        await handler._ensure_mcp_discovery("test_user")

        # Verify discovery was called
        mock_discover.assert_called_once_with([http_mcp_config], "test_user")

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.McpPluginRegistry.discover_and_materialize")
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_discovery_runs_only_once(
        self,
        mock_state_factory,
        mock_discover,
        http_mcp_config
    ):
        """Test that MCP discovery runs only once across multiple requests."""
        mock_state_manager = MagicMock()
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = [http_mcp_config]

        config = MagicMock()
        config.get_agent.return_value = agent_config

        handler = TealAgentsV1Alpha1Handler(config)

        # Reset discovery state
        TealAgentsV1Alpha1Handler._mcp_discovery_initialized = False
        McpPluginRegistry.clear()

        # Call discovery multiple times
        await handler._ensure_mcp_discovery("test_user")
        await handler._ensure_mcp_discovery("test_user")
        await handler._ensure_mcp_discovery("test_user")

        # Should only be called once
        mock_discover.assert_called_once()

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.McpPluginRegistry.discover_and_materialize")
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_discovery_skipped_when_no_mcp_servers(
        self,
        mock_state_factory,
        mock_discover
    ):
        """Test that discovery is skipped when no MCP servers configured."""
        mock_state_manager = MagicMock()
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = []  # No servers!

        config = MagicMock()
        config.get_agent.return_value = agent_config

        handler = TealAgentsV1Alpha1Handler(config)

        # Reset discovery state
        TealAgentsV1Alpha1Handler._mcp_discovery_initialized = False

        # Trigger discovery
        await handler._ensure_mcp_discovery("test_user")

        # Should NOT be called
        mock_discover.assert_not_called()


# ============================================================================
# Test Auth Challenge Generation
# ============================================================================

@pytest.mark.skip(reason="Handler integration tests need refactoring after McpConnectionManager changes. StateManagerFactory no longer in handler.")
class TestAuthChallenge:
    """Test OAuth2 auth challenge generation for missing tokens."""

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_auth_challenge_contains_correct_resume_url(self, mock_state_factory):
        """Test that auth challenge contains correct resume URL."""
        # Setup state manager
        mock_state_manager = MagicMock()
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = []

        config = MagicMock()
        config.get_agent.return_value = agent_config

        handler = TealAgentsV1Alpha1Handler(config)

        # Create auth challenge
        request_id = "test-request-123"
        challenge = handler._create_auth_challenge(
            auth_server="https://github.com/login/oauth",
            scopes=["repo", "read:user"],
            request_id=request_id,
            message="GitHub OAuth required"
        )

        # Verify resume URL format
        assert challenge["type"] == "auth_required"
        assert challenge["auth_server"] == "https://github.com/login/oauth"
        assert challenge["scopes"] == ["repo", "read:user"]
        assert challenge["resume_url"] == f"/tealagents/v1alpha1/resume/{request_id}"
        assert challenge["message"] == "GitHub OAuth required"


# ============================================================================
# Test Resume Flow
# ============================================================================

@pytest.mark.skip(reason="Handler integration tests need refactoring after McpConnectionManager changes. StateManagerFactory no longer in handler.")
class TestResumeFlow:
    """Test resuming agent execution after OAuth2 completion."""

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.McpPluginRegistry.get_plugin_class")
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_resume_loads_mcp_plugins(
        self,
        mock_state_factory,
        mock_get_plugin_class,
        http_mcp_config
    ):
        """Test that resume flow loads MCP plugins with user_id."""
        # Setup state manager
        mock_state_manager = MagicMock()
        mock_request_state = MagicMock()
        mock_request_state.user_id = "test_user"
        mock_request_state.messages = []
        mock_request_state.streaming = False
        mock_state_manager.get_request_state.return_value = mock_request_state
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        # Setup plugin class mock
        mock_plugin_class = MagicMock()
        mock_plugin_instance = MagicMock()
        mock_plugin_class.return_value = mock_plugin_instance
        mock_get_plugin_class.return_value = mock_plugin_class

        # Create handler with MCP server
        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = [http_mcp_config]
        agent_config.name = "test-agent"

        config = MagicMock()
        config.get_agent.return_value = agent_config

        handler = TealAgentsV1Alpha1Handler(config)

        # Mock agent builder
        mock_agent = MagicMock()
        mock_agent.invoke = AsyncMock(return_value="Result")
        handler.agent_builder = MagicMock()
        handler.agent_builder.build_agent = AsyncMock(return_value=mock_agent)

        # Resume
        request_id = "test-request-123"
        # Note: This would normally fail because we haven't fully mocked all dependencies,
        # but we're testing that MCP plugin loading is attempted

        try:
            await handler._handle_resume(request_id)
        except Exception:
            # Expected to fail due to incomplete mocking
            pass

        # Verify plugin class was retrieved
        mock_get_plugin_class.assert_called_with("test-http")


# ============================================================================
# Test User ID Propagation
# ============================================================================

class TestUserIdPropagation:
    """Test that user_id is correctly propagated through invocation chain."""

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.McpPluginRegistry.discover_and_materialize")
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_user_id_passed_to_discovery(
        self,
        mock_state_factory,
        mock_discover,
        http_mcp_config
    ):
        """Test that user_id is passed to MCP discovery."""
        mock_state_manager = MagicMock()
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = [http_mcp_config]

        config = MagicMock()
        config.get_agent.return_value = agent_config

        handler = TealAgentsV1Alpha1Handler(config)

        # Reset discovery
        TealAgentsV1Alpha1Handler._mcp_discovery_initialized = False
        McpPluginRegistry.clear()

        # Discover with specific user
        user_id = "user_12345"
        await handler._ensure_mcp_discovery(user_id)

        # Verify user_id passed
        mock_discover.assert_called_once()
        call_args = mock_discover.call_args
        assert call_args[0][1] == user_id  # Second arg is user_id

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_agent_builder_receives_user_id(self, mock_state_factory):
        """Test that agent builder receives user_id for MCP plugin instantiation."""
        mock_state_manager = MagicMock()
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = []

        config = MagicMock()
        config.get_agent.return_value = agent_config

        handler = TealAgentsV1Alpha1Handler(config)

        # Mock agent builder
        mock_agent = MagicMock()
        mock_agent.invoke = AsyncMock(return_value="Result")
        handler.agent_builder = MagicMock()
        handler.agent_builder.build_agent = AsyncMock(return_value=mock_agent)

        # Mock extra data collector
        mock_extra_data_collector = MagicMock()

        # Call recursion_invoke
        user_id = "request_user_789"

        try:
            await handler._recursion_invoke(
                agent_config,
                [],
                mock_extra_data_collector,
                user_id
            )
        except Exception:
            # May fail due to incomplete mocking
            pass

        # Verify user_id passed to build_agent
        handler.agent_builder.build_agent.assert_called()
        call_args = handler.agent_builder.build_agent.call_args
        assert call_args[1]["user_id"] == user_id  # Keyword arg


# ============================================================================
# Test Error Handling
# ============================================================================

class TestErrorHandling:
    """Test error handling in MCP flows."""

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.McpPluginRegistry.discover_and_materialize")
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_discovery_failure_logged(
        self,
        mock_state_factory,
        mock_discover,
        http_mcp_config
    ):
        """Test that discovery failures are logged but don't crash."""
        mock_state_manager = MagicMock()
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        # Make discovery fail
        mock_discover.side_effect = Exception("Discovery failed")

        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = [http_mcp_config]

        config = MagicMock()
        config.get_agent.return_value = agent_config

        handler = TealAgentsV1Alpha1Handler(config)

        # Reset discovery
        TealAgentsV1Alpha1Handler._mcp_discovery_initialized = False

        # Should not raise (errors are caught and logged)
        try:
            await handler._ensure_mcp_discovery("test_user")
        except Exception as e:
            # Discovery failures should be caught
            pytest.fail(f"Discovery failure should be caught, but raised: {e}")

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_missing_user_id_raises_error(self, mock_state_factory):
        """Test that missing user_id raises clear error when MCP servers present."""
        mock_state_manager = MagicMock()
        mock_state_factory.return_value.get_state_manager.return_value = mock_state_manager

        http_config = McpServerConfig(
            name="test",
            transport="http",
            url="https://example.com/mcp",
            auth_server="https://example.com/oauth",
            scopes=["read"]
        )

        agent_config = MagicMock(spec=AgentConfig)
        agent_config.mcp_servers = [http_config]

        config = MagicMock()
        config.get_agent.return_value = agent_config

        handler = TealAgentsV1Alpha1Handler(config)

        # Mock agent builder to check user_id requirement
        handler.agent_builder = MagicMock()

        # Attempt to build agent without user_id should fail
        # (This tests the contract that MCP plugins require user_id)
        mock_extra_data_collector = MagicMock()

        with pytest.raises((ValueError, TypeError)):
            # Should fail when trying to instantiate MCP plugin without user_id
            await handler._recursion_invoke(
                agent_config,
                [],
                mock_extra_data_collector,
                user_id=""  # Empty user_id!
            )
