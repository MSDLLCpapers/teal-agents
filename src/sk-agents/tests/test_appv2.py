from types import NoneType
from unittest.mock import MagicMock, patch

import pytest
from a2a.types import AgentCapabilities, AgentCard, AgentProvider, AgentSkill
from fastapi import FastAPI
from pydantic import ValidationError
from redis.asyncio import Redis
from ska_utils import AppConfig

from sk_agents.a2a import RedisTaskStore
from sk_agents.appv2 import AppV2
from sk_agents.configs import (
    TA_A2A_ENABLED,
    TA_A2A_OUTPUT_CLASSIFIER_MODEL,
    TA_AGENT_BASE_URL,
    TA_PROVIDER_ORG,
    TA_PROVIDER_URL,
    TA_REDIS_DB,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_PWD,
    TA_REDIS_SSL,
    TA_REDIS_TTL,
    TA_SERVICE_CONFIG,
    TA_STATE_MANAGEMENT,
)
from sk_agents.ska_types import BaseConfig, BaseMultiModalInput
from sk_agents.state import RedisStateManager


@pytest.fixture
def mock_app_config():
    """Create a mock AppConfig."""
    config = MagicMock(spec=AppConfig)
    config.get.return_value = None
    return config


@pytest.fixture
def mock_base_config():
    """Create a mock BaseConfig."""
    config = MagicMock(spec=BaseConfig)
    config.apiVersion = "skagents/v2alpha1"
    config.name = "test-agent"
    config.version = "1.0.0"
    config.metadata = None
    return config


@pytest.fixture
def mock_fastapi_app():
    """Create a mock FastAPI app."""
    app = MagicMock(spec=FastAPI)
    app.include_router = MagicMock()
    return app


class TestGetUrl:
    """Test AppV2.get_url method."""

    def test_get_url_success(self, mock_app_config):
        """Test get_url returns correct URL format."""
        mock_app_config.get.return_value = "https://example.com"

        result = AppV2.get_url("my-agent", "1.0.0", mock_app_config)

        assert result == "https://example.com/my-agent/1.0.0/a2a"
        mock_app_config.get.assert_called_once_with(TA_AGENT_BASE_URL.env_name)

    def test_get_url_missing_base_url(self, mock_app_config):
        """Test get_url raises ValueError when base URL is missing."""
        mock_app_config.get.return_value = None

        with pytest.raises(ValueError, match="Base URL is not provided in the app config"):
            AppV2.get_url("my-agent", "1.0.0", mock_app_config)

    def test_get_url_empty_base_url(self, mock_app_config):
        """Test get_url raises ValueError when base URL is empty string."""
        mock_app_config.get.return_value = ""

        with pytest.raises(ValueError, match="Base URL is not provided in the app config"):
            AppV2.get_url("my-agent", "1.0.0", mock_app_config)


class TestGetProvider:
    """Test AppV2.get_provider method."""

    def test_get_provider_success(self, mock_app_config):
        """Test get_provider returns AgentProvider with correct values."""
        mock_app_config.get.side_effect = lambda key: {
            TA_PROVIDER_ORG.env_name: "TestOrg",
            TA_PROVIDER_URL.env_name: "https://testorg.com",
        }.get(key)

        result = AppV2.get_provider(mock_app_config)

        assert isinstance(result, AgentProvider)
        assert result.organization == "TestOrg"
        assert result.url == "https://testorg.com"

    def test_get_provider_with_none_values(self, mock_app_config):
        """Test get_provider raises validation error with None values."""
        mock_app_config.get.return_value = None

        with pytest.raises(ValidationError):
            AppV2.get_provider(mock_app_config)


class TestGetAgentCard:
    """Test AppV2.get_agent_card method."""

    def test_get_agent_card_success(self, mock_app_config, mock_base_config):
        """Test get_agent_card returns complete AgentCard."""
        # Setup metadata with skills
        mock_skill = MagicMock()
        mock_skill.id = "skill1"
        mock_skill.name = "Test Skill"
        mock_skill.description = "A test skill"
        mock_skill.tags = ["test"]
        mock_skill.examples = ["example1"]
        mock_skill.input_modes = ["text"]
        mock_skill.output_modes = ["text"]

        mock_metadata = MagicMock()
        mock_metadata.description = "Test Agent Description"
        mock_metadata.documentation_url = "https://docs.example.com"
        mock_metadata.skills = [mock_skill]

        mock_base_config.metadata = mock_metadata
        mock_base_config.name = "test-agent"
        mock_base_config.version = "1.0.0"

        mock_app_config.get.side_effect = lambda key: {
            TA_AGENT_BASE_URL.env_name: "https://api.example.com",
            TA_PROVIDER_ORG.env_name: "TestOrg",
            TA_PROVIDER_URL.env_name: "https://testorg.com",
        }.get(key)

        result = AppV2.get_agent_card(mock_base_config, mock_app_config)

        assert isinstance(result, AgentCard)
        assert result.name == "test-agent"
        assert result.version == "1.0.0"
        assert result.description == "Test Agent Description"
        assert result.url == "https://api.example.com/test-agent/1.0.0/a2a"
        assert result.documentationUrl == "https://docs.example.com"
        assert isinstance(result.capabilities, AgentCapabilities)
        assert result.capabilities.streaming is True
        assert result.capabilities.pushNotifications is False
        assert result.capabilities.stateTransitionHistory is True
        assert result.defaultInputModes == ["text"]
        assert result.defaultOutputModes == ["text"]
        assert len(result.skills) == 1
        assert isinstance(result.skills[0], AgentSkill)
        assert result.skills[0].id == "skill1"

    def test_get_agent_card_missing_metadata(self, mock_app_config, mock_base_config):
        """Test get_agent_card raises ValueError when metadata is None."""
        mock_base_config.metadata = None

        with pytest.raises(ValueError, match="Agent card metadata is not provided in the config"):
            AppV2.get_agent_card(mock_base_config, mock_app_config)

    def test_get_agent_card_missing_name(self, mock_app_config, mock_base_config):
        """Test get_agent_card raises ValueError when name is missing."""
        mock_metadata = MagicMock()
        mock_base_config.metadata = mock_metadata
        mock_base_config.name = None

        with pytest.raises(ValueError, match="Agent name is not provided in the config"):
            AppV2.get_agent_card(mock_base_config, mock_app_config)

    def test_get_agent_card_empty_name(self, mock_app_config, mock_base_config):
        """Test get_agent_card raises ValueError when name is empty string."""
        mock_metadata = MagicMock()
        mock_base_config.metadata = mock_metadata
        mock_base_config.name = ""

        with pytest.raises(ValueError, match="Agent name is not provided in the config"):
            AppV2.get_agent_card(mock_base_config, mock_app_config)


class TestGetRedisClient:
    """Test AppV2._get_redis_client method."""

    @patch("sk_agents.appv2.Redis")
    @patch("sk_agents.appv2.strtobool")
    def test_get_redis_client_all_params(self, mock_strtobool, mock_redis_class, mock_app_config):
        """Test _get_redis_client with all parameters."""
        mock_app_config.get.side_effect = lambda key: {
            TA_REDIS_HOST.env_name: "localhost",
            TA_REDIS_PORT.env_name: "6379",
            TA_REDIS_DB.env_name: "1",
            TA_REDIS_SSL.env_name: "true",
            TA_REDIS_PWD.env_name: "secret",
        }.get(key)
        mock_strtobool.return_value = True

        result = AppV2._get_redis_client(mock_app_config)

        mock_redis_class.assert_called_once_with(
            host="localhost",
            port=6379,
            db=1,
            ssl=True,
            password="secret",
        )
        assert result is mock_redis_class.return_value

    @patch("sk_agents.appv2.Redis")
    @patch("sk_agents.appv2.strtobool")
    def test_get_redis_client_minimal_params(
        self, mock_strtobool, mock_redis_class, mock_app_config
    ):
        """Test _get_redis_client with minimal parameters."""
        mock_app_config.get.side_effect = lambda key: {
            TA_REDIS_HOST.env_name: "redis.example.com",
            TA_REDIS_PORT.env_name: "6380",
            TA_REDIS_DB.env_name: None,
            TA_REDIS_SSL.env_name: "false",
            TA_REDIS_PWD.env_name: None,
        }.get(key)
        mock_strtobool.return_value = False

        AppV2._get_redis_client(mock_app_config)

        mock_redis_class.assert_called_once_with(
            host="redis.example.com",
            port=6380,
            db=0,
            ssl=False,
            password=None,
        )

    def test_get_redis_client_missing_host(self, mock_app_config):
        """Test _get_redis_client raises ValueError when host is missing."""
        mock_app_config.get.side_effect = lambda key: {
            TA_REDIS_HOST.env_name: None,
            TA_REDIS_PORT.env_name: "6379",
            TA_REDIS_SSL.env_name: "false",
            TA_REDIS_DB.env_name: "0",
            TA_REDIS_PWD.env_name: None,
        }.get(key)

        with pytest.raises(ValueError, match="Redis host must be provided for Redis task store"):
            AppV2._get_redis_client(mock_app_config)

    def test_get_redis_client_missing_port(self, mock_app_config):
        """Test _get_redis_client raises ValueError when port is missing."""
        mock_app_config.get.side_effect = lambda key: {
            TA_REDIS_HOST.env_name: "localhost",
            TA_REDIS_PORT.env_name: None,
            TA_REDIS_SSL.env_name: "false",
            TA_REDIS_DB.env_name: "0",
            TA_REDIS_PWD.env_name: None,
        }.get(key)

        with pytest.raises(ValueError, match="Redis port must be provided for Redis task store"):
            AppV2._get_redis_client(mock_app_config)


class TestGetRedisTaskStore:
    """Test AppV2._get_redis_task_store method."""

    @patch("sk_agents.appv2.RedisTaskStore")
    @patch("sk_agents.appv2.AppV2._get_redis_client")
    def test_get_redis_task_store_with_ttl(
        self, mock_get_redis_client, mock_redis_task_store_class, mock_app_config
    ):
        """Test _get_redis_task_store with TTL."""
        mock_redis_client = MagicMock(spec=Redis)
        mock_get_redis_client.return_value = mock_redis_client
        mock_app_config.get.return_value = "3600"

        result = AppV2._get_redis_task_store(mock_app_config)

        mock_app_config.get.assert_called_once_with(TA_REDIS_TTL.env_name)
        mock_redis_task_store_class.assert_called_once_with(
            redis_client=mock_redis_client,
            ttl=3600,
        )
        assert result is mock_redis_task_store_class.return_value

    @patch("sk_agents.appv2.RedisTaskStore")
    @patch("sk_agents.appv2.AppV2._get_redis_client")
    def test_get_redis_task_store_without_ttl(
        self, mock_get_redis_client, mock_redis_task_store_class, mock_app_config
    ):
        """Test _get_redis_task_store without TTL."""
        mock_redis_client = MagicMock(spec=Redis)
        mock_get_redis_client.return_value = mock_redis_client
        mock_app_config.get.return_value = None

        AppV2._get_redis_task_store(mock_app_config)

        mock_redis_task_store_class.assert_called_once_with(
            redis_client=mock_redis_client,
            ttl=None,
        )


class TestGetRedisStateManager:
    """Test AppV2._get_redis_state_manager method."""

    @patch("sk_agents.appv2.RedisStateManager")
    @patch("sk_agents.appv2.AppV2._get_redis_client")
    def test_get_redis_state_manager_with_ttl(
        self, mock_get_redis_client, mock_redis_state_manager_class, mock_app_config
    ):
        """Test _get_redis_state_manager with TTL."""
        mock_redis_client = MagicMock(spec=Redis)
        mock_get_redis_client.return_value = mock_redis_client
        mock_app_config.get.return_value = "7200"

        result = AppV2._get_redis_state_manager(mock_app_config)

        mock_app_config.get.assert_called_once_with(TA_REDIS_TTL.env_name)
        mock_redis_state_manager_class.assert_called_once_with(
            redis_client=mock_redis_client,
            ttl=7200,
        )
        assert result is mock_redis_state_manager_class.return_value

    @patch("sk_agents.appv2.RedisStateManager")
    @patch("sk_agents.appv2.AppV2._get_redis_client")
    def test_get_redis_state_manager_without_ttl(
        self, mock_get_redis_client, mock_redis_state_manager_class, mock_app_config
    ):
        """Test _get_redis_state_manager without TTL."""
        mock_redis_client = MagicMock(spec=Redis)
        mock_get_redis_client.return_value = mock_redis_client
        mock_app_config.get.return_value = None

        AppV2._get_redis_state_manager(mock_app_config)

        mock_redis_state_manager_class.assert_called_once_with(
            redis_client=mock_redis_client,
            ttl=None,
        )


class TestGetTaskStore:
    """Test AppV2._get_task_store method."""

    @patch("sk_agents.appv2.AppV2._get_redis_task_store")
    def test_get_task_store_redis(self, mock_get_redis_task_store, mock_app_config):
        """Test _get_task_store returns Redis task store."""
        mock_app_config.get.return_value = "redis"
        mock_redis_store = MagicMock(spec=RedisTaskStore)
        mock_get_redis_task_store.return_value = mock_redis_store

        result = AppV2._get_task_store(mock_app_config)

        mock_app_config.get.assert_called_once_with(TA_STATE_MANAGEMENT.env_name)
        mock_get_redis_task_store.assert_called_once_with(mock_app_config)
        assert result is mock_redis_store

    @patch("sk_agents.appv2.InMemoryTaskStore")
    def test_get_task_store_in_memory(self, mock_in_memory_class, mock_app_config):
        """Test _get_task_store returns in-memory task store."""
        mock_app_config.get.return_value = "in-memory"

        result = AppV2._get_task_store(mock_app_config)

        mock_in_memory_class.assert_called_once()
        assert result is mock_in_memory_class.return_value

    @patch("sk_agents.appv2.InMemoryTaskStore")
    def test_get_task_store_default(self, mock_in_memory_class, mock_app_config):
        """Test _get_task_store defaults to in-memory when value is None."""
        mock_app_config.get.return_value = None

        AppV2._get_task_store(mock_app_config)

        mock_in_memory_class.assert_called_once()

    @patch("sk_agents.appv2.InMemoryTaskStore")
    def test_get_task_store_unknown_value(self, mock_in_memory_class, mock_app_config):
        """Test _get_task_store defaults to in-memory for unknown values."""
        mock_app_config.get.return_value = "unknown-store"

        AppV2._get_task_store(mock_app_config)

        mock_in_memory_class.assert_called_once()


class TestGetStateManager:
    """Test AppV2._get_state_manager method."""

    @patch("sk_agents.appv2.AppV2._get_redis_state_manager")
    def test_get_state_manager_redis(self, mock_get_redis_state_manager, mock_app_config):
        """Test _get_state_manager returns Redis state manager."""
        mock_app_config.get.return_value = "redis"
        mock_redis_manager = MagicMock(spec=RedisStateManager)
        mock_get_redis_state_manager.return_value = mock_redis_manager

        result = AppV2._get_state_manager(mock_app_config)

        mock_app_config.get.assert_called_once_with(TA_STATE_MANAGEMENT.env_name)
        mock_get_redis_state_manager.assert_called_once_with(mock_app_config)
        assert result is mock_redis_manager

    @patch("sk_agents.appv2.InMemoryStateManager")
    def test_get_state_manager_in_memory(self, mock_in_memory_class, mock_app_config):
        """Test _get_state_manager returns in-memory state manager."""
        mock_app_config.get.return_value = "in-memory"

        result = AppV2._get_state_manager(mock_app_config)

        mock_in_memory_class.assert_called_once()
        assert result is mock_in_memory_class.return_value

    @patch("sk_agents.appv2.InMemoryStateManager")
    def test_get_state_manager_default(self, mock_in_memory_class, mock_app_config):
        """Test _get_state_manager defaults to in-memory when value is None."""
        mock_app_config.get.return_value = None

        AppV2._get_state_manager(mock_app_config)

        mock_in_memory_class.assert_called_once()


class TestRun:
    """Test AppV2.run method."""

    @patch("sk_agents.appv2.Routes")
    @patch("sk_agents.appv2.initialize_plugin_loader")
    @patch("sk_agents.appv2.strtobool")
    def test_run_without_a2a(
        self,
        mock_strtobool,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
    ):
        """Test run without A2A enabled."""
        config_file = "/path/to/agents/config.yaml"
        mock_app_config.get.side_effect = lambda key: {
            TA_A2A_ENABLED.env_name: "false",
            TA_SERVICE_CONFIG.env_name: config_file,
        }.get(key)
        mock_strtobool.return_value = False
        mock_base_config.name = "test-agent"
        mock_base_config.metadata = None

        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        AppV2.run(
            name="test-agent",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        # Verify plugin loader initialized
        mock_initialize_plugin_loader.assert_called_once_with(
            agents_path="/path/to/agents", app_config=mock_app_config
        )

        # Verify REST routes registered
        mock_routes_class.get_rest_routes.assert_called_once()
        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["name"] == "test-agent"
        assert rest_call.kwargs["version"] == "1.0.0"
        assert rest_call.kwargs["description"] == "test-agent API"
        assert rest_call.kwargs["root_handler_name"] == "skagents"
        assert rest_call.kwargs["input_class"] is BaseMultiModalInput
        assert rest_call.kwargs["output_class"] is NoneType

        # Verify WebSocket routes registered
        mock_routes_class.get_websocket_routes.assert_called_once()

        # Verify A2A routes NOT registered
        mock_routes_class.get_a2a_routes.assert_not_called()

        # Verify routers added to app
        assert mock_fastapi_app.include_router.call_count == 2

    @patch("sk_agents.appv2.Routes")
    @patch("sk_agents.appv2.initialize_plugin_loader")
    @patch("sk_agents.appv2.strtobool")
    def test_run_with_metadata_description(
        self,
        mock_strtobool,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
    ):
        """Test run uses metadata description when available."""
        config_file = "/path/to/agents/config.yaml"
        mock_metadata = MagicMock()
        mock_metadata.description = "Custom Agent Description"
        mock_base_config.metadata = mock_metadata

        mock_app_config.get.side_effect = lambda key: {
            TA_A2A_ENABLED.env_name: "false",
            TA_SERVICE_CONFIG.env_name: config_file,
        }.get(key)
        mock_strtobool.return_value = False

        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        AppV2.run(
            name="test-agent",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["description"] == "Custom Agent Description"

    @patch("sk_agents.appv2.Routes")
    @patch("sk_agents.appv2.initialize_plugin_loader")
    @patch("sk_agents.appv2.strtobool")
    def test_run_with_metadata_no_description(
        self,
        mock_strtobool,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
    ):
        """Test run uses default description when metadata has None description."""
        config_file = "/path/to/agents/config.yaml"
        mock_metadata = MagicMock()
        mock_metadata.description = None
        mock_base_config.metadata = mock_metadata
        mock_base_config.name = "my-agent"

        mock_app_config.get.side_effect = lambda key: {
            TA_A2A_ENABLED.env_name: "false",
            TA_SERVICE_CONFIG.env_name: config_file,
        }.get(key)
        mock_strtobool.return_value = False

        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        AppV2.run(
            name="my-agent",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["description"] == "my-agent API"

    @patch("sk_agents.appv2.AppV2._get_state_manager")
    @patch("sk_agents.appv2.AppV2._get_task_store")
    @patch("sk_agents.appv2.ChatCompletionBuilder")
    @patch("sk_agents.appv2.Routes")
    @patch("sk_agents.appv2.initialize_plugin_loader")
    @patch("sk_agents.appv2.strtobool")
    def test_run_with_a2a_enabled(
        self,
        mock_strtobool,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_chat_completion_builder_class,
        mock_get_task_store,
        mock_get_state_manager,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
    ):
        """Test run with A2A enabled."""
        config_file = "/path/to/agents/config.yaml"
        model_name = "gpt-4"
        mock_app_config.get.side_effect = lambda key: {
            TA_A2A_ENABLED.env_name: "true",
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_A2A_OUTPUT_CLASSIFIER_MODEL.env_name: model_name,
        }.get(key)
        mock_strtobool.return_value = True
        mock_base_config.metadata = None

        # Setup mocks
        mock_chat_builder = MagicMock()
        mock_chat_completion_builder_class.return_value = mock_chat_builder
        mock_task_store = MagicMock()
        mock_get_task_store.return_value = mock_task_store
        mock_state_manager = MagicMock()
        mock_get_state_manager.return_value = mock_state_manager

        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()
        mock_routes_class.get_a2a_routes.return_value = MagicMock()

        AppV2.run(
            name="test-agent",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        # Verify ChatCompletionBuilder created
        mock_chat_completion_builder_class.assert_called_once_with(mock_app_config)
        mock_chat_builder.get_chat_completion_for_model.assert_called_once_with(
            "test-to-confirm-model-availability", model_name
        )

        # Verify task store and state manager retrieved
        mock_get_task_store.assert_called_once_with(mock_app_config)
        mock_get_state_manager.assert_called_once_with(mock_app_config)

        # Verify A2A routes registered
        mock_routes_class.get_a2a_routes.assert_called_once()
        a2a_call = mock_routes_class.get_a2a_routes.call_args
        assert a2a_call.kwargs["name"] == "test-agent"
        assert a2a_call.kwargs["version"] == "1.0.0"
        assert a2a_call.kwargs["chat_completion_builder"] is mock_chat_builder
        assert a2a_call.kwargs["task_store"] is mock_task_store
        assert a2a_call.kwargs["state_manager"] is mock_state_manager

        # Verify all routers added to app (REST, WebSocket, A2A)
        assert mock_fastapi_app.include_router.call_count == 3

        # Verify A2A router has correct prefix
        a2a_router_call = mock_fastapi_app.include_router.call_args_list[2]
        assert a2a_router_call[1]["prefix"] == "/test-agent/1.0.0/a2a"

    @patch("sk_agents.appv2.Routes")
    @patch("sk_agents.appv2.initialize_plugin_loader")
    @patch("sk_agents.appv2.strtobool")
    def test_run_extracts_root_handler_from_apiversion(
        self,
        mock_strtobool,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
    ):
        """Test run extracts root handler from apiVersion."""
        config_file = "/path/to/agents/config.yaml"
        mock_base_config.apiVersion = "tealagents/v2alpha1"
        mock_base_config.metadata = None

        mock_app_config.get.side_effect = lambda key: {
            TA_A2A_ENABLED.env_name: "false",
            TA_SERVICE_CONFIG.env_name: config_file,
        }.get(key)
        mock_strtobool.return_value = False

        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        AppV2.run(
            name="test-agent",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["root_handler_name"] == "tealagents"

        ws_call = mock_routes_class.get_websocket_routes.call_args
        assert ws_call.kwargs["root_handler_name"] == "tealagents"

    @patch("sk_agents.appv2.Routes")
    @patch("sk_agents.appv2.initialize_plugin_loader")
    @patch("sk_agents.appv2.strtobool")
    def test_run_router_prefix_format(
        self,
        mock_strtobool,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
    ):
        """Test that routers are registered with correct prefix format."""
        config_file = "/path/to/agents/config.yaml"
        mock_app_config.get.side_effect = lambda key: {
            TA_A2A_ENABLED.env_name: "false",
            TA_SERVICE_CONFIG.env_name: config_file,
        }.get(key)
        mock_strtobool.return_value = False
        mock_base_config.metadata = None

        mock_rest_router = MagicMock()
        mock_ws_router = MagicMock()
        mock_routes_class.get_rest_routes.return_value = mock_rest_router
        mock_routes_class.get_websocket_routes.return_value = mock_ws_router

        AppV2.run(
            name="my-agent",
            version="2.5.1",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        assert mock_fastapi_app.include_router.call_count == 2
        call1 = mock_fastapi_app.include_router.call_args_list[0]
        call2 = mock_fastapi_app.include_router.call_args_list[1]

        # First call should be REST router
        assert call1[0][0] is mock_rest_router
        assert call1[1]["prefix"] == "/my-agent/2.5.1"

        # Second call should be WebSocket router
        assert call2[0][0] is mock_ws_router
        assert call2[1]["prefix"] == "/my-agent/2.5.1"
