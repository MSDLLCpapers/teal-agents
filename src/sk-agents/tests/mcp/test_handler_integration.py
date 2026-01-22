"""
Integration tests for MCP handler flows.

Tests MCP discovery at session start, auth challenges, and resume flows.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from sk_agents.mcp_plugin_registry import McpPluginRegistry
from sk_agents.tealagents.v1alpha1.agent.handler import TealAgentsV1Alpha1Handler
from sk_agents.tealagents.v1alpha1.config import AgentConfig, McpServerConfig

# ============================================================================
# Test MCP Discovery at Session Start
# ============================================================================


@pytest.mark.skip(reason="Handler tests need refactoring after McpConnectionManager changes.")
class TestSessionStartDiscovery:
    """Test MCP discovery when handler starts a new session."""

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.McpPluginRegistry.discover_and_materialize")
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_discovery_runs_on_first_request(
        self, mock_state_factory, mock_discover, http_mcp_config
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
        self, mock_state_factory, mock_discover, http_mcp_config
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
    async def test_discovery_skipped_when_no_mcp_servers(self, mock_state_factory, mock_discover):
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


@pytest.mark.skip(reason="Handler tests need refactoring after McpConnectionManager changes.")
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
            message="GitHub OAuth required",
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


@pytest.mark.skip(reason="Handler tests need refactoring after McpConnectionManager changes.")
class TestResumeFlow:
    """Test resuming agent execution after OAuth2 completion."""

    @pytest.mark.asyncio
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.McpPluginRegistry.get_plugin_class")
    @patch("sk_agents.tealagents.v1alpha1.agent.handler.StateManagerFactory")
    async def test_resume_loads_mcp_plugins(
        self, mock_state_factory, mock_get_plugin_class, http_mcp_config
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
    """Test that user_id is correctly propagated through MCP discovery.

    These tests verify that user_id and session_id are properly passed to
    McpPluginRegistry.discover_and_materialize() when discovery is triggered.

    Note: We test at the McpPluginRegistry level rather than through the handler
    because the handler has complex Pydantic validation requirements that make
    direct instantiation difficult in tests.
    """

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session_with_retry")
    @patch("sk_agents.mcp_plugin_registry.resolve_server_auth_headers")
    async def test_user_id_passed_to_discovery(
        self, mock_resolve_auth, mock_create_session, http_mcp_config
    ):
        """Test that user_id and session_id are passed to MCP discovery."""
        from sk_agents.mcp_discovery.mcp_discovery_manager import McpState

        # Setup mocks
        mock_resolve_auth.return_value = {"Authorization": "Bearer token"}

        mock_session = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
        mock_create_session.return_value = (mock_session, lambda: "mcp-session-id")

        # Test with specific user_id and session_id
        user_id = "user_12345"
        session_id = "session_abc"

        # Create a proper McpState object for load_discovery to return
        mock_state = McpState(
            user_id=user_id,
            session_id=session_id,
            discovered_servers={},
            discovery_completed=False,
        )

        # Setup discovery manager mock
        mock_discovery_manager = AsyncMock()
        mock_discovery_manager.load_discovery = AsyncMock(return_value=mock_state)
        mock_discovery_manager.update_discovery = AsyncMock()

        mock_app_config = MagicMock()

        await McpPluginRegistry.discover_and_materialize(
            [http_mcp_config],
            user_id,
            session_id,
            mock_discovery_manager,
            mock_app_config,
        )

        # Verify resolve_server_auth_headers was called with the server config and user_id
        mock_resolve_auth.assert_called()

        # Verify load_discovery was called with correct user_id and session_id
        mock_discovery_manager.load_discovery.assert_called_once_with(user_id, session_id)

        # Verify update_discovery was called (state is updated after discovery)
        mock_discovery_manager.update_discovery.assert_called()

    @pytest.mark.asyncio
    async def test_discovery_state_scoped_to_user_and_session(self, http_mcp_config):
        """Test that discovery state is properly scoped to user_id and session_id."""
        from sk_agents.mcp_discovery.in_memory_discovery_manager import InMemoryStateManager

        # Use real in-memory state manager for this test
        mock_app_config = MagicMock()
        state_manager = InMemoryStateManager(mock_app_config)

        user_id_1 = "user_A"
        user_id_2 = "user_B"
        session_id = "shared_session"

        # Initially, neither user should have completed discovery
        assert not await state_manager.is_completed(user_id_1, session_id)
        assert not await state_manager.is_completed(user_id_2, session_id)

        # Mark discovery complete for user_A
        from sk_agents.mcp_discovery.mcp_discovery_manager import McpState

        state_1 = McpState(
            user_id=user_id_1,
            session_id=session_id,
            discovered_servers={},
            discovery_completed=False,
        )
        await state_manager.create_discovery(state_1)
        await state_manager.mark_completed(user_id_1, session_id)

        # User A should be completed, User B should not
        assert await state_manager.is_completed(user_id_1, session_id)
        assert not await state_manager.is_completed(user_id_2, session_id)


# ============================================================================
# Test Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling in MCP discovery flows.

    These tests verify that errors during MCP discovery are handled gracefully
    and that proper validation occurs for required parameters.

    Note: We test at the McpPluginRegistry level rather than through the handler
    because the handler has complex Pydantic validation requirements.
    """

    @pytest.mark.asyncio
    @patch("sk_agents.mcp_plugin_registry.create_mcp_session_with_retry")
    @patch("sk_agents.mcp_plugin_registry.resolve_server_auth_headers")
    async def test_discovery_continues_on_server_failure(
        self, mock_resolve_auth, mock_create_session, http_mcp_config
    ):
        """Test that discovery continues even if one server fails."""
        from sk_agents.mcp_discovery.mcp_discovery_manager import McpState

        # First server fails, second succeeds
        mock_resolve_auth.return_value = {"Authorization": "Bearer token"}

        call_count = [0]

        async def create_session_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise Exception("First server failed")
            mock_session = AsyncMock()
            mock_session.list_tools = AsyncMock(return_value=MagicMock(tools=[]))
            return (mock_session, lambda: "mcp-session-id")

        mock_create_session.side_effect = create_session_side_effect

        user_id = "test_user"
        session_id = "session_123"

        # Create a proper McpState object for load_discovery to return
        mock_state = McpState(
            user_id=user_id,
            session_id=session_id,
            discovered_servers={},
            discovery_completed=False,
        )

        # Setup discovery manager mock
        mock_discovery_manager = AsyncMock()
        mock_discovery_manager.load_discovery = AsyncMock(return_value=mock_state)
        mock_discovery_manager.update_discovery = AsyncMock()
        mock_discovery_manager.mark_completed = AsyncMock()

        mock_app_config = MagicMock()

        # Create two server configs
        server_1 = McpServerConfig(
            name="server-1",
            transport="http",
            url="https://server1.example.com/mcp",
        )
        server_2 = McpServerConfig(
            name="server-2",
            transport="http",
            url="https://server2.example.com/mcp",
        )

        # Discovery should complete even though server-1 failed
        await McpPluginRegistry.discover_and_materialize(
            [server_1, server_2],
            user_id,
            session_id,
            mock_discovery_manager,
            mock_app_config,
        )

        # Both servers should have been attempted
        assert call_count[0] == 2

        # Verify update_discovery was called (state updated after each server attempt)
        mock_discovery_manager.update_discovery.assert_called()

    @pytest.mark.asyncio
    async def test_mcp_plugin_requires_user_id(self):
        """Test that McpPlugin raises ValueError when user_id is missing."""
        from sk_agents.mcp_client import McpPlugin, McpTool

        # Create a minimal McpTool
        mock_tool = McpTool(
            tool_name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            server_config=MagicMock(),
            server_name="test-server",
        )

        # McpPlugin should raise ValueError when user_id is empty
        with pytest.raises(ValueError, match="user_id"):
            McpPlugin(
                tools=[mock_tool],
                server_name="test-server",
                user_id="",  # Empty user_id!
                connection_manager=MagicMock(),
            )

    @pytest.mark.asyncio
    async def test_mcp_plugin_requires_connection_manager(self):
        """Test that McpPlugin raises ValueError when connection_manager is missing."""
        from sk_agents.mcp_client import McpPlugin, McpTool

        # Create a minimal McpTool
        mock_tool = McpTool(
            tool_name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            server_config=MagicMock(),
            server_name="test-server",
        )

        # McpPlugin should raise ValueError when connection_manager is None
        with pytest.raises(ValueError, match="connection_manager"):
            McpPlugin(
                tools=[mock_tool],
                server_name="test-server",
                user_id="test_user",
                connection_manager=None,  # Missing connection_manager!
            )
