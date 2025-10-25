"""
Unit tests for MCP client components.

Tests authentication, configuration, and tool execution without real OAuth2 or MCP servers.
"""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.mcp_client import (
    McpPlugin,
    McpTool,
    build_auth_storage_key,
    map_mcp_annotations_to_governance,
    apply_trust_level_governance,
    apply_governance_overrides,
    resolve_server_auth_headers,
)
from sk_agents.plugin_catalog.models import Governance, GovernanceOverride
from sk_agents.tealagents.v1alpha1.config import McpServerConfig


# ============================================================================
# Test Auth Storage Key Builder
# ============================================================================

class TestAuthStorageKeyBuilder:
    """Test the build_auth_storage_key utility function."""

    def test_build_key_with_scopes(self):
        """Test key building with multiple scopes."""
        key = build_auth_storage_key(
            "https://github.com/login/oauth",
            ["repo", "read:user"]
        )
        assert key == "https://github.com/login/oauth|read:user|repo"

    def test_build_key_scopes_sorted(self):
        """Test that scopes are sorted for consistency."""
        key1 = build_auth_storage_key("https://example.com", ["b", "a", "c"])
        key2 = build_auth_storage_key("https://example.com", ["c", "a", "b"])
        assert key1 == key2 == "https://example.com|a|b|c"

    def test_build_key_no_scopes(self):
        """Test key building with no scopes."""
        key = build_auth_storage_key("https://example.com", [])
        assert key == "https://example.com"

    def test_build_key_empty_scopes_list(self):
        """Test key building with empty list."""
        key = build_auth_storage_key("https://example.com", [])
        assert key == "https://example.com"


# ============================================================================
# Test Governance Mapping
# ============================================================================

class TestGovernanceMapping:
    """Test mapping MCP annotations to governance policies."""

    def test_map_destructive_tool(self):
        """Test mapping destructive tool annotations."""
        annotations = {"destructiveHint": True}
        governance = map_mcp_annotations_to_governance(annotations)

        assert governance.requires_hitl is True
        assert governance.cost == "high"
        assert governance.data_sensitivity == "sensitive"

    def test_map_readonly_tool(self):
        """Test mapping read-only tool annotations."""
        annotations = {"readOnlyHint": True}
        governance = map_mcp_annotations_to_governance(annotations)

        assert governance.requires_hitl is False
        assert governance.cost == "low"
        assert governance.data_sensitivity == "public"

    def test_map_unknown_tool_secure_by_default(self):
        """Test that unknown tools default to secure settings."""
        annotations = {}
        governance = map_mcp_annotations_to_governance(annotations)

        assert governance.requires_hitl is True  # Secure by default!
        assert governance.cost == "high"
        assert governance.data_sensitivity == "sensitive"

    def test_map_with_risky_description(self):
        """Test governance mapping with risky keywords in description."""
        annotations = {}
        description = "Execute command on remote server"
        governance = map_mcp_annotations_to_governance(annotations, description)

        assert governance.requires_hitl is True
        assert governance.cost == "high"

    def test_map_with_network_keywords(self):
        """Test detection of network operations."""
        annotations = {}
        description = "Fetch data from https://api.example.com"
        governance = map_mcp_annotations_to_governance(annotations, description)

        assert governance.requires_hitl is True
        assert governance.data_sensitivity == "sensitive"


# ============================================================================
# Test Trust Level Governance
# ============================================================================

class TestTrustLevelGovernance:
    """Test trust level governance application."""

    def test_untrusted_server_forces_hitl(self):
        """Test that untrusted servers force HITL for all tools."""
        base_governance = Governance(
            requires_hitl=False,
            cost="low",
            data_sensitivity="public"
        )

        final_governance = apply_trust_level_governance(
            base_governance,
            "untrusted",
            "Read file from filesystem"
        )

        assert final_governance.requires_hitl is True  # Forced!
        assert final_governance.cost == "high"  # Elevated!

    def test_sandboxed_server_requires_hitl(self):
        """Test that sandboxed servers require HITL."""
        base_governance = Governance(
            requires_hitl=False,
            cost="low",
            data_sensitivity="public"
        )

        final_governance = apply_trust_level_governance(
            base_governance,
            "sandboxed",
            "List files"
        )

        assert final_governance.requires_hitl is True  # Sandboxed = HITL required

    def test_trusted_server_with_safe_operation(self):
        """Test that trusted servers allow safe operations without HITL."""
        base_governance = Governance(
            requires_hitl=False,
            cost="low",
            data_sensitivity="public"
        )

        final_governance = apply_trust_level_governance(
            base_governance,
            "trusted",
            "Read configuration value"
        )

        assert final_governance.requires_hitl is False  # Allowed!
        assert final_governance.cost == "low"

    def test_trusted_server_with_risky_operation(self):
        """Test that even trusted servers enforce HITL for risky operations."""
        base_governance = Governance(
            requires_hitl=False,
            cost="low",
            data_sensitivity="public"
        )

        final_governance = apply_trust_level_governance(
            base_governance,
            "trusted",
            "Delete all files from directory"  # Risky!
        )

        assert final_governance.requires_hitl is True  # Defense in depth!
        assert final_governance.cost == "high"


# ============================================================================
# Test Governance Overrides
# ============================================================================

class TestGovernanceOverrides:
    """Test manual governance override application."""

    def test_override_hitl_requirement(self):
        """Test overriding HITL requirement."""
        base_governance = Governance(
            requires_hitl=True,
            cost="high",
            data_sensitivity="sensitive"
        )

        overrides = {
            "test_tool": GovernanceOverride(
                requires_hitl=False,  # Override!
                cost=None,  # Keep base
                data_sensitivity=None  # Keep base
            )
        }

        final_governance = apply_governance_overrides(
            base_governance,
            "test_tool",
            overrides
        )

        assert final_governance.requires_hitl is False  # Overridden
        assert final_governance.cost == "high"  # Kept from base
        assert final_governance.data_sensitivity == "sensitive"  # Kept from base

    def test_override_all_fields(self):
        """Test overriding all governance fields."""
        base_governance = Governance(
            requires_hitl=True,
            cost="high",
            data_sensitivity="sensitive"
        )

        overrides = {
            "test_tool": GovernanceOverride(
                requires_hitl=False,
                cost="low",
                data_sensitivity="public"
            )
        }

        final_governance = apply_governance_overrides(
            base_governance,
            "test_tool",
            overrides
        )

        assert final_governance.requires_hitl is False
        assert final_governance.cost == "low"
        assert final_governance.data_sensitivity == "public"

    def test_no_override_for_tool(self):
        """Test that missing override returns base governance."""
        base_governance = Governance(
            requires_hitl=True,
            cost="high",
            data_sensitivity="sensitive"
        )

        overrides = {
            "other_tool": GovernanceOverride(requires_hitl=False, cost="low", data_sensitivity="public")
        }

        final_governance = apply_governance_overrides(
            base_governance,
            "test_tool",  # Not in overrides!
            overrides
        )

        assert final_governance == base_governance  # Unchanged

    def test_no_overrides_dict(self):
        """Test that None overrides returns base governance."""
        base_governance = Governance(
            requires_hitl=True,
            cost="high",
            data_sensitivity="sensitive"
        )

        final_governance = apply_governance_overrides(
            base_governance,
            "test_tool",
            None
        )

        assert final_governance == base_governance


# ============================================================================
# Test Auth Header Resolution
# ============================================================================

class TestAuthHeaderResolution:
    """Test OAuth2 token resolution for MCP servers."""

    @patch("sk_agents.mcp_client.AuthStorageFactory")
    def test_resolve_with_valid_token(self, mock_factory_class, mock_oauth2_token):
        """Test resolving headers with valid OAuth2 token."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage.retrieve.return_value = mock_oauth2_token
        mock_factory = MagicMock()
        mock_factory.get_auth_storage_manager.return_value = mock_storage
        mock_factory_class.return_value = mock_factory

        # Create config
        config = McpServerConfig(
            name="github",
            transport="http",
            url="https://api.github.com/mcp",
            auth_server="https://github.com/login/oauth",
            scopes=["repo", "read:user"]
        )

        # Resolve headers
        headers = resolve_server_auth_headers(config, "test_user")

        # Verify
        assert "Authorization" in headers
        assert headers["Authorization"] == "Bearer mock_access_token_12345"

    @patch("sk_agents.mcp_client.AuthStorageFactory")
    def test_resolve_with_expired_token(self, mock_factory_class, expired_oauth2_token):
        """Test that expired tokens are not used."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage.retrieve.return_value = expired_oauth2_token
        mock_factory = MagicMock()
        mock_factory.get_auth_storage_manager.return_value = mock_storage
        mock_factory_class.return_value = mock_factory

        config = McpServerConfig(
            name="test",
            transport="http",
            url="https://api.example.com/mcp",
            auth_server="https://example.com/oauth",
            scopes=["read"]
        )

        headers = resolve_server_auth_headers(config, "test_user")

        # Should NOT include Authorization header for expired token
        assert "Authorization" not in headers

    @patch("sk_agents.mcp_client.AuthStorageFactory")
    def test_resolve_with_no_token(self, mock_factory_class):
        """Test resolving headers when no token is stored."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage.retrieve.return_value = None  # No token stored
        mock_factory = MagicMock()
        mock_factory.get_auth_storage_manager.return_value = mock_storage
        mock_factory_class.return_value = mock_factory

        config = McpServerConfig(
            name="test",
            transport="http",
            url="https://api.example.com/mcp",
            auth_server="https://example.com/oauth",
            scopes=["read"]
        )

        headers = resolve_server_auth_headers(config, "test_user")

        # Should return empty headers
        assert headers == {}

    @patch("sk_agents.mcp_client.AuthStorageFactory")
    def test_resolve_forwards_non_sensitive_headers(self, mock_factory_class, mock_oauth2_token):
        """Test that non-sensitive custom headers are forwarded."""
        # Setup mocks
        mock_storage = MagicMock()
        mock_storage.retrieve.return_value = mock_oauth2_token
        mock_factory = MagicMock()
        mock_factory.get_auth_storage_manager.return_value = mock_storage
        mock_factory_class.return_value = mock_factory

        config = McpServerConfig(
            name="test",
            transport="http",
            url="https://api.example.com/mcp",
            auth_server="https://example.com/oauth",
            scopes=["read"],
            headers={
                "X-Client-Version": "1.0",
                "X-Request-ID": "12345"
            }
        )

        headers = resolve_server_auth_headers(config, "test_user")

        # Should include both OAuth2 and custom headers
        assert headers["Authorization"] == "Bearer mock_access_token_12345"
        assert headers["X-Client-Version"] == "1.0"
        assert headers["X-Request-ID"] == "12345"

    def test_resolve_blocks_static_authorization(self):
        """Test that static Authorization headers are blocked at config validation."""
        # Config validation should prevent static Authorization headers
        with pytest.raises(ValueError, match="Static Authorization headers are no longer supported"):
            McpServerConfig(
                name="test",
                transport="http",
                url="https://api.example.com/mcp",
                auth_server="https://example.com/oauth",
                scopes=["read"],
                headers={
                    "Authorization": "Bearer static_token",  # Should be blocked!
                    "X-Client": "test"
                }
            )


# ============================================================================
# Test McpTool
# ============================================================================

class TestMcpTool:
    """Test stateless MCP tool wrapper."""

    def test_tool_initialization(self, http_mcp_config):
        """Test creating an MCP tool."""
        tool = McpTool(
            tool_name="test_tool",
            description="A test tool",
            input_schema={"type": "object", "properties": {}},
            output_schema=None,
            server_config=http_mcp_config,
            server_name="test-server",
        )

        assert tool.tool_name == "test_tool"
        assert tool.description == "A test tool"
        assert tool.server_name == "test-server"
        assert tool.server_config == http_mcp_config

    @pytest.mark.asyncio
    async def test_tool_input_validation(self, http_mcp_config):
        """Test that tool validates required inputs."""
        tool = McpTool(
            tool_name="test_tool",
            description="A test tool",
            input_schema={
                "type": "object",
                "properties": {
                    "required_param": {"type": "string"}
                },
                "required": ["required_param"]
            },
            output_schema=None,
            server_config=http_mcp_config,
            server_name="test-server",
        )

        # Should raise RuntimeError wrapping ValueError for missing required parameter
        with pytest.raises(RuntimeError, match="MCP tool 'test_tool' failed"):
            await tool.invoke("test_user", optional_param="value")


# ============================================================================
# Test McpPlugin
# ============================================================================

class TestMcpPlugin:
    """Test MCP plugin wrapper."""

    def test_plugin_requires_user_id(self, http_mcp_config):
        """Test that McpPlugin requires user_id."""
        tool = McpTool(
            tool_name="test_tool",
            description="Test",
            input_schema={},
            output_schema=None,
            server_config=http_mcp_config,
            server_name="test",
        )

        # Should raise ValueError without user_id
        with pytest.raises(ValueError, match="MCP plugins require a user_id"):
            McpPlugin(
                tools=[tool],
                server_name="test",
                user_id="",  # Empty user_id!
                authorization=None,
                extra_data_collector=None
            )

    def test_plugin_initialization_with_user_id(self, http_mcp_config):
        """Test successful plugin initialization with user_id."""
        tool = McpTool(
            tool_name="test_tool",
            description="Test",
            input_schema={},
            output_schema=None,
            server_config=http_mcp_config,
            server_name="test",
        )

        plugin = McpPlugin(
            tools=[tool],
            server_name="test",
            user_id="test_user",
            authorization="Bearer token",
            extra_data_collector=None
        )

        assert plugin.user_id == "test_user"
        assert plugin.server_name == "test"
        assert plugin.authorization == "Bearer token"
        assert len(plugin.tools) == 1

    def test_plugin_creates_kernel_functions(self, http_mcp_config):
        """Test that plugin creates kernel functions for each tool."""
        tool1 = McpTool(
            tool_name="tool_one",
            description="First tool",
            input_schema={},
            output_schema=None,
            server_config=http_mcp_config,
            server_name="test",
        )

        tool2 = McpTool(
            tool_name="tool_two",
            description="Second tool",
            input_schema={},
            output_schema=None,
            server_config=http_mcp_config,
            server_name="test",
        )

        plugin = McpPlugin(
            tools=[tool1, tool2],
            server_name="test",
            user_id="test_user"
        )

        # Should create functions for both tools
        assert hasattr(plugin, "test_tool_one")
        assert hasattr(plugin, "test_tool_two")
