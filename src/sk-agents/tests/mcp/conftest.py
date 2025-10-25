"""
Pytest fixtures for MCP testing.

Provides mock OAuth2 storage, mock MCP servers, and test utilities.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest
from mcp import ClientSession
from mcp.types import Tool, TextContent

from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.mcp_plugin_registry import McpPluginRegistry
from sk_agents.tealagents.v1alpha1.config import McpServerConfig


# ============================================================================
# OAuth2 Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_oauth2_token():
    """Create a mock OAuth2 token that's valid for 1 hour."""
    return OAuth2AuthData(
        access_token="mock_access_token_12345",
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        refresh_token="mock_refresh_token_67890",
        scopes=["repo", "read:user"],
    )


@pytest.fixture
def expired_oauth2_token():
    """Create an expired OAuth2 token for testing expiration handling."""
    return OAuth2AuthData(
        access_token="expired_token",
        token_type="Bearer",
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Expired 1 hour ago
        refresh_token="expired_refresh",
        scopes=["repo"],
    )


@pytest.fixture
def mock_auth_storage(mock_oauth2_token):
    """
    Create a mock auth storage manager with pre-populated OAuth2 tokens.

    Simulates InMemorySecureAuthStorageManager behavior.
    """
    storage = MagicMock()

    # Mock storage dictionary
    _storage: Dict[str, Dict[str, OAuth2AuthData]] = {
        "test_user": {
            "https://github.com/login/oauth|read:user|repo": mock_oauth2_token,
            "https://api.example.com/oauth2|read|write": mock_oauth2_token,
        }
    }

    def retrieve(user_id: str, key: str) -> OAuth2AuthData | None:
        return _storage.get(user_id, {}).get(key)

    def store(user_id: str, key: str, auth_data: OAuth2AuthData):
        if user_id not in _storage:
            _storage[user_id] = {}
        _storage[user_id][key] = auth_data

    storage.retrieve = Mock(side_effect=retrieve)
    storage.store = Mock(side_effect=store)

    return storage


@pytest.fixture
def mock_auth_storage_factory(mock_auth_storage):
    """Create a mock AuthStorageFactory that returns mock auth storage."""
    factory = MagicMock()
    factory.get_auth_storage_manager.return_value = mock_auth_storage
    return factory


# ============================================================================
# MCP Server Config Fixtures
# ============================================================================

@pytest.fixture
def stdio_mcp_config():
    """Create a valid stdio MCP server config."""
    return McpServerConfig(
        name="test-stdio",
        transport="stdio",
        command="npx",
        args=["@modelcontextprotocol/server-filesystem", "/tmp/test"],
        env={"NODE_ENV": "test"},
    )


@pytest.fixture
def http_mcp_config():
    """Create a valid HTTP MCP server config with OAuth2."""
    return McpServerConfig(
        name="test-http",
        transport="http",
        url="https://api.example.com/mcp",
        auth_server="https://api.example.com/oauth2",
        scopes=["read", "write"],
        timeout=30.0,
        headers={"X-Test-Client": "mcp-test"},
    )


@pytest.fixture
def github_mcp_config():
    """Create a GitHub-like MCP server config."""
    return McpServerConfig(
        name="github",
        transport="http",
        url="https://api.github.com/mcp",
        auth_server="https://github.com/login/oauth",
        scopes=["repo", "read:user"],
        tool_governance_overrides={
            "create_repository": {
                "requires_hitl": False,
                "cost": "medium",
            },
            "delete_repository": {
                "requires_hitl": True,
                "cost": "high",
            },
        },
    )


# ============================================================================
# Mock MCP SDK Components
# ============================================================================

@pytest.fixture
def mock_mcp_tool():
    """Create a mock MCP tool with realistic structure."""
    tool = MagicMock(spec=Tool)
    tool.name = "test_tool"
    tool.description = "A test tool for MCP"
    tool.inputSchema = {
        "type": "object",
        "properties": {
            "param1": {"type": "string", "description": "First parameter"},
            "param2": {"type": "integer", "description": "Second parameter"},
        },
        "required": ["param1"],
    }
    tool.annotations = {"readOnlyHint": True}
    return tool


@pytest.fixture
def mock_destructive_tool():
    """Create a mock destructive MCP tool."""
    tool = MagicMock(spec=Tool)
    tool.name = "delete_resource"
    tool.description = "Delete a resource (destructive operation)"
    tool.inputSchema = {
        "type": "object",
        "properties": {
            "resource_id": {"type": "string"},
        },
        "required": ["resource_id"],
    }
    tool.annotations = {"destructiveHint": True}
    return tool


@pytest.fixture
def mock_mcp_session(mock_mcp_tool):
    """
    Create a mock MCP ClientSession with realistic behavior.

    This mocks the MCP SDK's ClientSession to avoid actual server connections.
    """
    session = AsyncMock(spec=ClientSession)

    # Mock initialize
    init_result = MagicMock()
    init_result.server_info = {"name": "test-server", "version": "1.0.0"}
    init_result.protocol_version = "2025-03-26"
    session.initialize = AsyncMock(return_value=init_result)

    # Mock list_tools
    tools_result = MagicMock()
    tools_result.tools = [mock_mcp_tool]
    session.list_tools = AsyncMock(return_value=tools_result)

    # Mock call_tool
    tool_result = MagicMock()
    tool_result.content = [TextContent(text="Tool execution result")]
    session.call_tool = AsyncMock(return_value=tool_result)

    return session


@pytest.fixture
def mock_stdio_client(mock_mcp_session):
    """Mock the stdio_client context manager."""
    async def mock_context():
        # Return mock read/write streams
        read = AsyncMock()
        write = AsyncMock()
        return read, write

    return mock_context


# ============================================================================
# Test Utilities
# ============================================================================

@pytest.fixture
def reset_mcp_registry():
    """Reset McpPluginRegistry between tests."""
    yield
    McpPluginRegistry.clear()


@pytest.fixture(autouse=True)
def cleanup_mcp_registry():
    """Automatically cleanup McpPluginRegistry after each test."""
    yield
    McpPluginRegistry.clear()


# ============================================================================
# App Config Mocks
# ============================================================================

@pytest.fixture
def mock_app_config():
    """Create a mock AppConfig for testing."""
    config = MagicMock()
    config.get.return_value = None  # Default: no config values
    return config


# ============================================================================
# Kernel & Plugin Mocks
# ============================================================================

@pytest.fixture
def mock_kernel():
    """Create a mock Semantic Kernel."""
    from semantic_kernel import Kernel

    kernel = MagicMock(spec=Kernel)
    kernel.add_plugin = Mock()
    return kernel


@pytest.fixture
def mock_extra_data_collector():
    """Create a mock ExtraDataCollector."""
    from sk_agents.extra_data_collector import ExtraDataCollector

    collector = MagicMock(spec=ExtraDataCollector)
    collector.get_extra_data.return_value = {}
    return collector
