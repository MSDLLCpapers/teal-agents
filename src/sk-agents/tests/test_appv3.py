from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from ska_utils import AppConfig

from sk_agents.appv3 import AppV3
from sk_agents.ska_types import BaseConfig
from sk_agents.tealagents.v1alpha1.agent.config import Spec
from sk_agents.tealagents.v1alpha1.config import AgentConfig


@pytest.fixture
def mock_app_config():
    """Create a mock AppConfig for testing."""
    config = MagicMock(spec=AppConfig)
    config.get = MagicMock(return_value=None)
    return config


@pytest.fixture
def mock_base_config():
    """Create a mock BaseConfig for testing."""
    agent_config = AgentConfig(name="TestAgent", model="gpt-4o", system_prompt="test prompt")

    config = BaseConfig(
        apiVersion="tealagents/v1alpha1",
        name="TestAgent",
        version=0.1,
        description="test agent",
        spec=Spec(agent=agent_config),
    )
    config.metadata = MagicMock()
    config.metadata.description = "Test description"
    return config


@pytest.fixture
def mock_fastapi_app():
    """Create a mock FastAPI app for testing."""
    app = MagicMock(spec=FastAPI)
    app.state = MagicMock()
    app.include_router = MagicMock()
    return app


class TestAppV3StateStores:
    """Test the StateStores enum."""

    def test_state_stores_enum_values(self):
        """Test that StateStores enum has the correct values."""
        assert AppV3.StateStores.IN_MEMORY.value == "in-memory"
        assert AppV3.StateStores.REDIS.value == "redis"


class TestAppV3GetRedisClient:
    """Test the _get_redis_client static method."""

    def test_get_redis_client_success(self, mock_app_config):
        """Test successful Redis client creation."""
        # Configure mock to return Redis configuration values
        mock_app_config.get.side_effect = lambda key: {
            "TA_REDIS_HOST": "localhost",
            "TA_REDIS_PORT": "6379",
            "TA_REDIS_DB": "0",
            "TA_REDIS_SSL": "false",
            "TA_REDIS_PWD": "password",
        }.get(key)

        with patch("sk_agents.appv3.Redis") as mock_redis:
            result = AppV3._get_redis_client(mock_app_config)

            mock_redis.assert_called_once_with(
                host="localhost", port=6379, db=0, ssl=False, password="password"
            )
            assert result == mock_redis.return_value

    def test_get_redis_client_no_host_raises_error(self, mock_app_config):
        """Test that missing Redis host raises ValueError."""
        mock_app_config.get.side_effect = lambda key: {
            "TA_REDIS_SSL": "true"  # Default value for SSL
        }.get(key)

        with pytest.raises(ValueError, match="Redis host must be provided"):
            AppV3._get_redis_client(mock_app_config)

    def test_get_redis_client_no_port_raises_error(self, mock_app_config):
        """Test that missing Redis port raises ValueError."""
        mock_app_config.get.side_effect = lambda key: {
            "TA_REDIS_HOST": "localhost",
            "TA_REDIS_SSL": "true",  # Default value for SSL
        }.get(key)

        with pytest.raises(ValueError, match="Redis port must be provided"):
            AppV3._get_redis_client(mock_app_config)

    def test_get_redis_client_with_defaults(self, mock_app_config):
        """Test Redis client creation with default values."""
        mock_app_config.get.side_effect = lambda key: {
            "TA_REDIS_HOST": "localhost",
            "TA_REDIS_PORT": "6379",
            "TA_REDIS_SSL": "true",  # Default value for SSL
        }.get(key)

        with patch("sk_agents.appv3.Redis") as mock_redis:
            AppV3._get_redis_client(mock_app_config)

            mock_redis.assert_called_once_with(
                host="localhost", port=6379, db=0, ssl=True, password=None
            )


class TestAppV3StateManager:
    """Test the _get_state_manager static method."""

    @patch("sk_agents.appv3.PersistenceFactory")
    def test_get_state_manager(self, mock_persistence_factory, mock_app_config):
        """Test state manager creation."""
        mock_factory_instance = MagicMock()
        mock_state_manager = MagicMock()
        mock_factory_instance.get_persistence_manager.return_value = mock_state_manager
        mock_persistence_factory.return_value = mock_factory_instance

        result = AppV3._get_state_manager(mock_app_config)

        mock_persistence_factory.assert_called_once_with(mock_app_config)
        mock_factory_instance.get_persistence_manager.assert_called_once()
        assert result == mock_state_manager


class TestAppV3AuthStorageManager:
    """Test the _get_auth_storage_manager static method."""

    @patch("sk_agents.appv3.AuthStorageFactory")
    def test_get_auth_storage_manager(self, mock_auth_storage_factory, mock_app_config):
        """Test auth storage manager creation."""
        mock_factory_instance = MagicMock()
        mock_auth_storage_manager = MagicMock()
        mock_factory_instance.get_auth_storage_manager.return_value = mock_auth_storage_manager
        mock_auth_storage_factory.return_value = mock_factory_instance

        result = AppV3._get_auth_storage_manager(mock_app_config)

        mock_auth_storage_factory.assert_called_once_with(mock_app_config)
        mock_factory_instance.get_auth_storage_manager.assert_called_once()
        assert result == mock_auth_storage_manager


class TestAppV3AuthManager:
    """Test the _get_auth_manager static method."""

    @patch("sk_agents.appv3.MockAuthenticationManager")
    def test_get_auth_manager(self, mock_auth_manager_class, mock_app_config):
        """Test auth manager creation."""
        mock_auth_manager = MagicMock()
        mock_auth_manager_class.return_value = mock_auth_manager

        result = AppV3._get_auth_manager(mock_app_config)

        mock_auth_manager_class.assert_called_once()
        assert result == mock_auth_manager


class TestAppV3ChatCompletionsBuilder:
    """Test the _create_chat_completions_builder static method."""

    @patch("sk_agents.appv3.ChatCompletionBuilder")
    def test_create_chat_completions_builder(self, mock_builder_class, mock_app_config):
        """Test chat completions builder creation."""
        mock_builder = MagicMock()
        mock_builder_class.return_value = mock_builder

        result = AppV3._create_chat_completions_builder(mock_app_config)

        mock_builder_class.assert_called_once_with(mock_app_config)
        assert result == mock_builder


class TestAppV3RemotePluginLoader:
    """Test the _create_remote_plugin_loader static method."""

    @patch("sk_agents.appv3.RemotePluginLoader")
    @patch("sk_agents.appv3.RemotePluginCatalog")
    def test_create_remote_plugin_loader(
        self, mock_catalog_class, mock_loader_class, mock_app_config
    ):
        """Test remote plugin loader creation."""
        mock_catalog = MagicMock()
        mock_loader = MagicMock()
        mock_catalog_class.return_value = mock_catalog
        mock_loader_class.return_value = mock_loader

        result = AppV3._create_remote_plugin_loader(mock_app_config)

        mock_catalog_class.assert_called_once_with(mock_app_config)
        mock_loader_class.assert_called_once_with(mock_catalog)
        assert result == mock_loader


class TestAppV3KernelBuilder:
    """Test the _create_kernel_builder static method."""

    @patch("sk_agents.appv3.KernelBuilder")
    @patch.object(AppV3, "_create_remote_plugin_loader")
    @patch.object(AppV3, "_create_chat_completions_builder")
    def test_create_kernel_builder(
        self, mock_chat_builder, mock_plugin_loader, mock_kernel_builder_class, mock_app_config
    ):
        """Test kernel builder creation."""
        mock_chat_completions = MagicMock()
        mock_remote_plugin_loader = MagicMock()
        mock_kernel_builder = MagicMock()

        mock_chat_builder.return_value = mock_chat_completions
        mock_plugin_loader.return_value = mock_remote_plugin_loader
        mock_kernel_builder_class.return_value = mock_kernel_builder

        authorization = "test_authorization"
        result = AppV3._create_kernel_builder(mock_app_config, authorization)

        mock_chat_builder.assert_called_once_with(mock_app_config)
        mock_plugin_loader.assert_called_once_with(mock_app_config)
        mock_kernel_builder_class.assert_called_once_with(
            mock_chat_completions, mock_remote_plugin_loader, mock_app_config, authorization
        )
        assert result == mock_kernel_builder


class TestAppV3Run:
    """Test the main run method."""

    def test_run_invalid_api_version_raises_error(self, mock_app_config, mock_fastapi_app):
        """Test that invalid API version raises ValueError."""
        config = MagicMock()
        config.apiVersion = "invalid/version"

        with pytest.raises(ValueError, match="AppV3 only supports 'tealagents/v1alpha1'"):
            AppV3.run("test", "v1", mock_app_config, config, mock_fastapi_app)

    @patch("sk_agents.appv3.initialize_plugin_loader")
    @patch.object(AppV3, "_get_auth_storage_manager")
    @patch.object(AppV3, "_get_auth_manager")
    @patch.object(AppV3, "_get_state_manager")
    @patch("sk_agents.appv3.Routes")
    @patch("sk_agents.appv3.UtilityRoutes")
    @patch("os.path.dirname")
    def test_run_success_with_metadata_description(
        self,
        mock_dirname,
        mock_utility_routes_class,
        mock_routes,
        mock_get_state_manager,
        mock_get_auth_manager,
        mock_get_auth_storage_manager,
        mock_initialize_plugin,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
    ):
        """Test successful run with metadata description."""
        # Setup mocks
        mock_app_config.get.return_value = "/path/to/config.yaml"
        mock_dirname.return_value = "/path/to"

        mock_state_manager = MagicMock()
        mock_auth_manager = MagicMock()
        mock_auth_storage_manager = MagicMock()

        mock_get_state_manager.return_value = mock_state_manager
        mock_get_auth_manager.return_value = mock_auth_manager
        mock_get_auth_storage_manager.return_value = mock_auth_storage_manager

        mock_stateful_router = MagicMock()
        mock_resume_router = MagicMock()
        mock_health_router = MagicMock()
        mock_routes.get_stateful_routes.return_value = mock_stateful_router
        mock_routes.get_resume_routes.return_value = mock_resume_router

        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = mock_health_router
        mock_utility_routes_class.return_value = mock_utility_routes

        # Execute
        AppV3.run("testapp", "v1", mock_app_config, mock_base_config, mock_fastapi_app)

        # Verify calls
        mock_initialize_plugin.assert_called_once_with(
            agents_path="/path/to", app_config=mock_app_config
        )
        mock_get_state_manager.assert_called_once_with(mock_app_config)
        mock_get_auth_manager.assert_called_once_with(mock_app_config)
        mock_get_auth_storage_manager.assert_called_once_with(mock_app_config)

        # Verify route setup
        mock_routes.get_stateful_routes.assert_called_once()
        stateful_call_args = mock_routes.get_stateful_routes.call_args
        assert stateful_call_args.kwargs["name"] == "testapp"
        assert stateful_call_args.kwargs["version"] == "v1"
        assert stateful_call_args.kwargs["description"] == "Test description"
        assert stateful_call_args.kwargs["config"] == mock_base_config
        assert stateful_call_args.kwargs["app_config"] == mock_app_config
        assert stateful_call_args.kwargs["state_manager"] == mock_state_manager
        assert stateful_call_args.kwargs["authorizer"] == mock_auth_manager
        assert stateful_call_args.kwargs["auth_storage_manager"] == mock_auth_storage_manager

        mock_routes.get_resume_routes.assert_called_once_with(
            config=mock_base_config, app_config=mock_app_config, state_manager=mock_state_manager
        )

        # Verify utility routes setup
        mock_utility_routes_class.assert_called_once()
        mock_utility_routes.get_health_routes.assert_called_once_with(
            config=mock_base_config, app_config=mock_app_config
        )

        # Verify router inclusion
        assert mock_fastapi_app.include_router.call_count == 3
        mock_fastapi_app.include_router.assert_any_call(mock_stateful_router, prefix="/testapp/v1")
        mock_fastapi_app.include_router.assert_any_call(mock_resume_router, prefix="/testapp/v1")
        mock_fastapi_app.include_router.assert_any_call(mock_health_router, prefix="/testapp/v1")

        # Verify app state setup
        assert mock_fastapi_app.state.config == mock_base_config
        assert mock_fastapi_app.state.app_config == mock_app_config

    @patch("sk_agents.appv3.initialize_plugin_loader")
    @patch.object(AppV3, "_get_auth_storage_manager")
    @patch.object(AppV3, "_get_auth_manager")
    @patch.object(AppV3, "_get_state_manager")
    @patch("sk_agents.appv3.Routes")
    @patch("sk_agents.appv3.UtilityRoutes")
    @patch("os.path.dirname")
    def test_run_success_without_metadata_description(
        self,
        mock_dirname,
        mock_utility_routes_class,
        mock_routes,
        mock_get_state_manager,
        mock_get_auth_manager,
        mock_get_auth_storage_manager,
        mock_initialize_plugin,
        mock_app_config,
        mock_fastapi_app,
    ):
        """Test successful run without metadata description."""
        # Create config without metadata
        config = BaseConfig(
            apiVersion="tealagents/v1alpha1",
            name="TestAgent",
            version=0.1,
            description="test agent",
            spec=Spec(agent=AgentConfig(name="TestAgent", model="gpt-4o", system_prompt="test")),
        )
        config.metadata = None

        # Setup mocks
        mock_app_config.get.return_value = "/path/to/config.yaml"
        mock_dirname.return_value = "/path/to"

        mock_state_manager = MagicMock()
        mock_auth_manager = MagicMock()
        mock_auth_storage_manager = MagicMock()

        mock_get_state_manager.return_value = mock_state_manager
        mock_get_auth_manager.return_value = mock_auth_manager
        mock_get_auth_storage_manager.return_value = mock_auth_storage_manager

        mock_stateful_router = MagicMock()
        mock_resume_router = MagicMock()
        mock_health_router = MagicMock()
        mock_routes.get_stateful_routes.return_value = mock_stateful_router
        mock_routes.get_resume_routes.return_value = mock_resume_router

        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = mock_health_router
        mock_utility_routes_class.return_value = mock_utility_routes

        # Execute
        AppV3.run("testapp", "v1", mock_app_config, config, mock_fastapi_app)

        # Verify fallback description is used
        stateful_call_args = mock_routes.get_stateful_routes.call_args
        assert stateful_call_args.kwargs["description"] == "TestAgent API"

    @patch("sk_agents.appv3.initialize_plugin_loader")
    @patch.object(AppV3, "_get_auth_storage_manager")
    @patch.object(AppV3, "_get_auth_manager")
    @patch.object(AppV3, "_get_state_manager")
    @patch("sk_agents.appv3.Routes")
    @patch("sk_agents.appv3.UtilityRoutes")
    @patch("os.path.dirname")
    def test_run_success_with_metadata_but_no_description(
        self,
        mock_dirname,
        mock_utility_routes_class,
        mock_routes,
        mock_get_state_manager,
        mock_get_auth_manager,
        mock_get_auth_storage_manager,
        mock_initialize_plugin,
        mock_app_config,
        mock_fastapi_app,
    ):
        """Test successful run with metadata but no description."""
        # Create config with metadata but no description
        config = BaseConfig(
            apiVersion="tealagents/v1alpha1",
            name="TestAgent",
            version=0.1,
            description="test agent",
            spec=Spec(agent=AgentConfig(name="TestAgent", model="gpt-4o", system_prompt="test")),
        )
        config.metadata = MagicMock()
        config.metadata.description = None

        # Setup mocks
        mock_app_config.get.return_value = "/path/to/config.yaml"
        mock_dirname.return_value = "/path/to"

        mock_state_manager = MagicMock()
        mock_auth_manager = MagicMock()
        mock_auth_storage_manager = MagicMock()

        mock_get_state_manager.return_value = mock_state_manager
        mock_get_auth_manager.return_value = mock_auth_manager
        mock_get_auth_storage_manager.return_value = mock_auth_storage_manager

        mock_stateful_router = MagicMock()
        mock_resume_router = MagicMock()
        mock_health_router = MagicMock()
        mock_routes.get_stateful_routes.return_value = mock_stateful_router
        mock_routes.get_resume_routes.return_value = mock_resume_router

        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = mock_health_router
        mock_utility_routes_class.return_value = mock_utility_routes

        # Execute
        AppV3.run("testapp", "v1", mock_app_config, config, mock_fastapi_app)

        # Verify fallback description is used
        stateful_call_args = mock_routes.get_stateful_routes.call_args
        assert stateful_call_args.kwargs["description"] == "TestAgent API"
