"""Tests for utility routes including health, liveness, and metadata endpoints."""

from unittest.mock import MagicMock, PropertyMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sk_agents.ska_types import BaseConfig, ConfigMetadata
from sk_agents.utility_routes import AgentMetadata, UtilityRoutes


class TestExtractMetadata:
    """Test UtilityRoutes._extract_metadata static method."""

    def test_extract_metadata_with_name_and_description(self):
        """Test metadata extraction with top-level name and description."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="my-agent",
            version="1.0",
            description="A helpful agent",
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.agent_name == "my-agent"
        assert metadata.description == "A helpful agent"
        assert metadata.model is None
        assert metadata.plugins is None

    def test_extract_metadata_with_service_name_fallback(self):
        """Test metadata extraction falls back to service_name when name is None."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            service_name="my-service",
            version="1.0",
            description="A service",
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.agent_name == "my-service"

    def test_extract_metadata_with_metadata_description(self):
        """Test metadata description takes precedence over top-level description."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="my-agent",
            version="1.0",
            description="Top-level description",
            metadata=ConfigMetadata(
                description="Metadata description",
                skills=[],
            ),
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.description == "Metadata description"

    def test_extract_metadata_falls_back_to_top_level_description(self):
        """Test fallback to top-level description when metadata description is None."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="my-agent",
            version="1.0",
            description="Top-level description",
        )
        config.metadata = None

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.description == "Top-level description"

    def test_extract_metadata_no_description(self):
        """Test metadata extraction when no description is available."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="my-agent",
            version="1.0",
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.description is None

    def test_extract_metadata_with_single_agent_spec(self):
        """Test metadata extraction with spec.agent (single agent config)."""
        mock_agent = MagicMock()
        mock_agent.model = "gpt-4o"
        mock_agent.plugins = ["PluginA", "PluginB"]
        mock_agent.remote_plugins = ["RemotePlugin"]
        mock_agent.mcp_servers = None

        mock_spec = MagicMock()
        mock_spec.agent = mock_agent
        mock_spec.agents = None  # Ensure no multi-agent attribute

        config = BaseConfig(
            apiVersion="skagents/v1",
            name="my-agent",
            version="1.0",
            description="Test",
            spec=mock_spec,
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.model == "gpt-4o"
        assert metadata.plugins == ["PluginA", "PluginB", "RemotePlugin"]

    def test_extract_metadata_with_mcp_servers(self):
        """Test metadata extraction includes MCP server names as plugins."""
        mock_mcp_server1 = MagicMock()
        mock_mcp_server1.name = "filesystem"
        mock_mcp_server2 = MagicMock()
        mock_mcp_server2.name = "github"

        mock_agent = MagicMock()
        mock_agent.model = "gpt-4"
        mock_agent.plugins = ["LocalPlugin"]
        mock_agent.remote_plugins = None
        mock_agent.mcp_servers = [mock_mcp_server1, mock_mcp_server2]

        mock_spec = MagicMock()
        mock_spec.agent = mock_agent
        mock_spec.agents = None

        config = BaseConfig(
            apiVersion="tealagents/v1alpha1",
            name="mcp-agent",
            version="1.0",
            description="MCP agent",
            spec=mock_spec,
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.model == "gpt-4"
        assert metadata.plugins == ["LocalPlugin", "mcp:filesystem", "mcp:github"]

    def test_extract_metadata_with_multi_agent_spec(self):
        """Test metadata extraction with spec.agents (sequential/multi-agent config)."""
        mock_agent1 = MagicMock()
        mock_agent1.model = "gpt-4o"
        mock_agent1.plugins = ["PluginA"]
        mock_agent1.remote_plugins = None

        mock_agent2 = MagicMock()
        mock_agent2.model = "gpt-4o-mini"
        mock_agent2.plugins = ["PluginB"]
        mock_agent2.remote_plugins = ["RemoteC"]

        mock_spec = MagicMock()
        mock_spec.agent = None  # No single agent
        mock_spec.agents = [mock_agent1, mock_agent2]

        config = BaseConfig(
            apiVersion="skagents/v1",
            name="multi-agent",
            version="1.0",
            description="Multi agent",
            spec=mock_spec,
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.model == "gpt-4o, gpt-4o-mini"
        assert "PluginA" in metadata.plugins
        assert "PluginB" in metadata.plugins
        assert "RemoteC" in metadata.plugins

    def test_extract_metadata_multi_agent_deduplicates_models(self):
        """Test that duplicate models in multi-agent are deduplicated."""
        mock_agent1 = MagicMock()
        mock_agent1.model = "gpt-4o"
        mock_agent1.plugins = None
        mock_agent1.remote_plugins = None

        mock_agent2 = MagicMock()
        mock_agent2.model = "gpt-4o"
        mock_agent2.plugins = None
        mock_agent2.remote_plugins = None

        mock_spec = MagicMock()
        mock_spec.agent = None
        mock_spec.agents = [mock_agent1, mock_agent2]

        config = BaseConfig(
            apiVersion="skagents/v1",
            name="multi-agent",
            version="1.0",
            spec=mock_spec,
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.model == "gpt-4o"

    def test_extract_metadata_multi_agent_deduplicates_plugins(self):
        """Test that duplicate plugins in multi-agent are deduplicated."""
        mock_agent1 = MagicMock()
        mock_agent1.model = "gpt-4o"
        mock_agent1.plugins = ["SharedPlugin", "PluginA"]
        mock_agent1.remote_plugins = None

        mock_agent2 = MagicMock()
        mock_agent2.model = "gpt-4o-mini"
        mock_agent2.plugins = ["SharedPlugin", "PluginB"]
        mock_agent2.remote_plugins = None

        mock_spec = MagicMock()
        mock_spec.agent = None
        mock_spec.agents = [mock_agent1, mock_agent2]

        config = BaseConfig(
            apiVersion="skagents/v1",
            name="multi-agent",
            version="1.0",
            spec=mock_spec,
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.plugins == ["SharedPlugin", "PluginA", "PluginB"]

    def test_extract_metadata_no_spec(self):
        """Test metadata extraction when spec is None."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="my-agent",
            version="1.0",
            description="No spec agent",
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.agent_name == "my-agent"
        assert metadata.description == "No spec agent"
        assert metadata.model is None
        assert metadata.plugins is None

    def test_extract_metadata_with_no_plugins(self):
        """Test metadata extraction when agent has no plugins."""
        mock_agent = MagicMock()
        mock_agent.model = "gpt-4o"
        mock_agent.plugins = None
        mock_agent.remote_plugins = None
        mock_agent.mcp_servers = None

        mock_spec = MagicMock()
        mock_spec.agent = mock_agent
        mock_spec.agents = None

        config = BaseConfig(
            apiVersion="skagents/v1",
            name="my-agent",
            version="1.0",
            spec=mock_spec,
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.model == "gpt-4o"
        assert metadata.plugins is None

    def test_extract_metadata_with_empty_plugins(self):
        """Test metadata extraction when agent has empty plugin lists."""
        mock_agent = MagicMock()
        mock_agent.model = "gpt-4o"
        mock_agent.plugins = []
        mock_agent.remote_plugins = []
        mock_agent.mcp_servers = []

        mock_spec = MagicMock()
        mock_spec.agent = mock_agent
        mock_spec.agents = None

        config = BaseConfig(
            apiVersion="skagents/v1",
            name="my-agent",
            version="1.0",
            spec=mock_spec,
        )

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.plugins is None

    def test_extract_metadata_returns_empty_on_exception(self):
        """Test that _extract_metadata returns empty AgentMetadata on unexpected errors."""
        config = MagicMock(spec=BaseConfig)
        type(config).name = PropertyMock(side_effect=RuntimeError("unexpected"))

        metadata = UtilityRoutes._extract_metadata(config)

        assert metadata.agent_name is None
        assert metadata.description is None
        assert metadata.model is None
        assert metadata.plugins is None

    def test_extract_metadata_logs_info_on_success(self):
        """Test that successful extraction logs an info message."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="log-test-agent",
            version="1.0",
        )

        with patch("sk_agents.utility_routes.logger") as mock_logger:
            UtilityRoutes._extract_metadata(config)
            mock_logger.info.assert_called_once_with(
                "Extracted metadata for agent: %s", "log-test-agent"
            )

    def test_extract_metadata_logs_exception_on_error(self):
        """Test that extraction failure logs an exception."""
        config = MagicMock(spec=BaseConfig)
        type(config).name = PropertyMock(side_effect=RuntimeError("bad config"))

        with patch("sk_agents.utility_routes.logger") as mock_logger:
            UtilityRoutes._extract_metadata(config)
            mock_logger.exception.assert_called_once()


class TestMetadataRoute:
    """Test the /metadata endpoint via FastAPI TestClient."""

    def test_metadata_endpoint_returns_agent_info(self):
        """Test that the /metadata endpoint returns correct agent metadata."""
        mock_agent = MagicMock()
        mock_agent.model = "gpt-4o"
        mock_agent.plugins = ["WeatherPlugin"]
        mock_agent.remote_plugins = None
        mock_agent.mcp_servers = None

        mock_spec = MagicMock()
        mock_spec.agent = mock_agent
        mock_spec.agents = None

        config = BaseConfig(
            apiVersion="skagents/v1",
            name="test-agent",
            version="1.0",
            description="A test agent",
            spec=mock_spec,
        )

        utility_routes = UtilityRoutes()
        router = utility_routes.get_metadata_routes(config=config)

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/metadata")

        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "test-agent"
        assert data["description"] == "A test agent"
        assert data["model"] == "gpt-4o"
        assert data["plugins"] == ["WeatherPlugin"]

    def test_metadata_endpoint_with_minimal_config(self):
        """Test metadata endpoint with minimal config (no spec)."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="minimal-agent",
            version="1.0",
        )

        utility_routes = UtilityRoutes()
        router = utility_routes.get_metadata_routes(config=config)

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/metadata")

        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "minimal-agent"
        assert data["description"] is None
        assert data["model"] is None
        assert data["plugins"] is None

    def test_metadata_endpoint_with_mcp_servers(self):
        """Test metadata endpoint includes MCP servers as plugins."""
        mock_mcp = MagicMock()
        mock_mcp.name = "filesystem"

        mock_agent = MagicMock()
        mock_agent.model = "gpt-4"
        mock_agent.plugins = None
        mock_agent.remote_plugins = None
        mock_agent.mcp_servers = [mock_mcp]

        mock_spec = MagicMock()
        mock_spec.agent = mock_agent
        mock_spec.agents = None

        config = BaseConfig(
            apiVersion="tealagents/v1alpha1",
            name="mcp-agent",
            version="1.0",
            description="MCP agent",
            spec=mock_spec,
        )

        utility_routes = UtilityRoutes()
        router = utility_routes.get_metadata_routes(config=config)

        app = FastAPI()
        app.include_router(router)

        client = TestClient(app)
        response = client.get("/metadata")

        assert response.status_code == 200
        data = response.json()
        assert data["plugins"] == ["mcp:filesystem"]


class TestAgentMetadataModel:
    """Test the AgentMetadata Pydantic model."""

    def test_agent_metadata_all_fields(self):
        """Test AgentMetadata with all fields populated."""
        metadata = AgentMetadata(
            agent_name="test-agent",
            description="A test agent",
            model="gpt-4o",
            plugins=["PluginA", "PluginB"],
        )
        assert metadata.agent_name == "test-agent"
        assert metadata.description == "A test agent"
        assert metadata.model == "gpt-4o"
        assert metadata.plugins == ["PluginA", "PluginB"]

    def test_agent_metadata_defaults_to_none(self):
        """Test AgentMetadata defaults all fields to None."""
        metadata = AgentMetadata()
        assert metadata.agent_name is None
        assert metadata.description is None
        assert metadata.model is None
        assert metadata.plugins is None

    def test_agent_metadata_serialization(self):
        """Test AgentMetadata JSON serialization."""
        metadata = AgentMetadata(
            agent_name="my-agent",
            description="desc",
            model="gpt-4o",
            plugins=["P1"],
        )
        data = metadata.model_dump()
        assert data == {
            "agent_name": "my-agent",
            "description": "desc",
            "model": "gpt-4o",
            "plugins": ["P1"],
        }


class TestSafeGet:
    """Test UtilityRoutes._safe_get static method with dicts and objects."""

    def test_safe_get_from_dict(self):
        """Test _safe_get retrieves values from a dict."""
        data = {"name": "agent1", "model": "gpt-4o"}
        assert UtilityRoutes._safe_get(data, "name") == "agent1"
        assert UtilityRoutes._safe_get(data, "model") == "gpt-4o"

    def test_safe_get_from_dict_missing_key(self):
        """Test _safe_get returns default for missing dict keys."""
        data = {"name": "agent1"}
        assert UtilityRoutes._safe_get(data, "missing") is None
        assert UtilityRoutes._safe_get(data, "missing", "fallback") == "fallback"

    def test_safe_get_from_object(self):
        """Test _safe_get retrieves attributes from an object."""
        obj = MagicMock()
        obj.name = "agent1"
        assert UtilityRoutes._safe_get(obj, "name") == "agent1"

    def test_safe_get_from_object_missing_attr(self):
        """Test _safe_get returns None for missing object attributes."""
        obj = MagicMock(spec=[])
        assert UtilityRoutes._safe_get(obj, "missing") is None


class TestExtractMetadataWithDictSpec:
    """Test _extract_metadata with dict-based specs (real YAML parsing scenario)."""

    def test_single_agent_dict_spec(self):
        """Test extraction from a single-agent dict spec."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="ChatBot",
            version="1.0",
            description="A chat bot",
            spec={
                "agent": {
                    "name": "default",
                    "model": "gpt-4o",
                    "plugins": ["PluginA", "PluginB"],
                    "remote_plugins": ["RemotePlugin"],
                }
            },
        )
        metadata = UtilityRoutes._extract_metadata(config)
        assert metadata.agent_name == "ChatBot"
        assert metadata.description == "A chat bot"
        assert metadata.model == "gpt-4o"
        assert metadata.plugins == ["PluginA", "PluginB", "RemotePlugin"]

    def test_multi_agent_dict_spec(self):
        """Test extraction from a multi-agent dict spec."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            service_name="WeatherAgent",
            version="0.1",
            description="An agent for retrieving temperature",
            spec={
                "agents": [
                    {
                        "name": "default",
                        "model": "gpt-4o-2024-05-13",
                        "plugins": ["WeatherPlugin"],
                    }
                ],
                "tasks": [{"name": "action_task", "task_no": 1}],
            },
        )
        metadata = UtilityRoutes._extract_metadata(config)
        assert metadata.agent_name == "WeatherAgent"
        assert metadata.description == "An agent for retrieving temperature"
        assert metadata.model == "gpt-4o-2024-05-13"
        assert metadata.plugins == ["WeatherPlugin"]

    def test_multi_agent_dict_spec_multiple_agents(self):
        """Test extraction with multiple agents combines models and deduplicates plugins."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="MultiAgent",
            version="1.0",
            spec={
                "agents": [
                    {"name": "agent1", "model": "gpt-4o", "plugins": ["PluginA"]},
                    {"name": "agent2", "model": "gpt-3.5", "plugins": ["PluginA", "PluginB"]},
                ],
            },
        )
        metadata = UtilityRoutes._extract_metadata(config)
        assert metadata.model == "gpt-4o, gpt-3.5"
        assert metadata.plugins == ["PluginA", "PluginB"]

    def test_dict_spec_with_mcp_servers(self):
        """Test extraction includes MCP server names prefixed with 'mcp:'."""
        config = BaseConfig(
            apiVersion="tealagents/v1alpha1",
            name="MCPAgent",
            version="1.0",
            spec={
                "agent": {
                    "name": "default",
                    "model": "gpt-4o",
                    "plugins": ["LocalPlugin"],
                    "mcp_servers": [
                        {"name": "filesystem", "url": "http://localhost:3000"},
                        {"name": "github", "url": "http://localhost:3001"},
                    ],
                }
            },
        )
        metadata = UtilityRoutes._extract_metadata(config)
        assert metadata.model == "gpt-4o"
        assert metadata.plugins == ["LocalPlugin", "mcp:filesystem", "mcp:github"]

    def test_dict_spec_no_plugins(self):
        """Test extraction returns None for plugins when none are configured."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            name="NoPluginAgent",
            version="1.0",
            spec={"agent": {"name": "default", "model": "gpt-4o"}},
        )
        metadata = UtilityRoutes._extract_metadata(config)
        assert metadata.model == "gpt-4o"
        assert metadata.plugins is None

    def test_dict_spec_endpoint_integration(self):
        """Test the /metadata endpoint returns correct data for dict-based specs."""
        config = BaseConfig(
            apiVersion="skagents/v1",
            service_name="WeatherAgent",
            version="0.1",
            description="An agent for weather",
            spec={
                "agents": [
                    {"name": "default", "model": "gpt-4o-2024-05-13", "plugins": ["WeatherPlugin"]}
                ],
                "tasks": [{"name": "action_task", "task_no": 1}],
            },
        )
        utility_routes = UtilityRoutes()
        router = utility_routes.get_metadata_routes(config=config)
        app = FastAPI()
        app.include_router(router)
        client = TestClient(app)
        response = client.get("/metadata")
        assert response.status_code == 200
        data = response.json()
        assert data["agent_name"] == "WeatherAgent"
        assert data["description"] == "An agent for weather"
        assert data["model"] == "gpt-4o-2024-05-13"
        assert data["plugins"] == ["WeatherPlugin"]
