import os
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from ska_utils import AppConfig

from sk_agents.appv1 import AppV1
from sk_agents.configs import TA_SERVICE_CONFIG, TA_TYPES_MODULE
from sk_agents.ska_types import BaseConfig


@pytest.fixture
def mock_app_config():
    """Create a mock AppConfig with necessary properties."""
    config = MagicMock(spec=AppConfig)
    config.props = {}
    return config


@pytest.fixture
def mock_base_config():
    """Create a mock BaseConfig."""
    config = MagicMock(spec=BaseConfig)
    config.apiVersion = "skagents/v1alpha1"
    config.service_name = "test-service"
    config.input_type = "TestInput"
    config.output_type = "TestOutput"
    config.description = "Test service description"
    return config


@pytest.fixture
def mock_fastapi_app():
    """Create a mock FastAPI app."""
    app = MagicMock(spec=FastAPI)
    app.include_router = MagicMock()
    return app


@pytest.fixture
def mock_type_loader():
    """Create a mock type loader."""
    loader = MagicMock()
    loader.get_type = MagicMock(side_effect=lambda x: MagicMock())
    return loader


@pytest.fixture
def mock_routes():
    """Create mock Routes."""
    routes = MagicMock()
    routes.get_rest_routes = MagicMock(return_value=MagicMock())
    routes.get_websocket_routes = MagicMock(return_value=MagicMock())
    return routes


class TestAppV1Run:
    """Test AppV1.run method."""

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.datetime")
    def test_run_with_all_config_properties(
        self,
        mock_datetime,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run with all config properties set."""
        config_file = "/path/to/agents/config.yaml"
        types_module = "/path/to/types.py"
        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: types_module,
        }.get(key)

        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_now = MagicMock()
        mock_datetime.now.return_value = mock_now

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        mock_app_config.get.assert_any_call(TA_SERVICE_CONFIG.env_name)
        mock_app_config.get.assert_any_call(TA_TYPES_MODULE.env_name)
        mock_get_type_loader.assert_called_once_with(types_module)
        mock_initialize_plugin_loader.assert_called_once_with(
            agents_path="/path/to/agents", app_config=mock_app_config
        )
        mock_type_loader.get_type.assert_any_call("TestInput")
        mock_type_loader.get_type.assert_any_call("TestOutput")

        # Verify REST routes were registered
        mock_routes_class.get_rest_routes.assert_called_once()
        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["name"] == "test-service"
        assert rest_call.kwargs["version"] == "1.0.0"
        assert rest_call.kwargs["description"] == "Test service description"
        assert rest_call.kwargs["root_handler_name"] == "skagents"
        assert rest_call.kwargs["config"] is mock_base_config
        assert rest_call.kwargs["app_config"] is mock_app_config

        # Verify WebSocket routes were registered
        mock_routes_class.get_websocket_routes.assert_called_once()
        ws_call = mock_routes_class.get_websocket_routes.call_args
        assert ws_call.kwargs["name"] == "test-service"
        assert ws_call.kwargs["version"] == "1.0.0"
        assert ws_call.kwargs["root_handler_name"] == "skagents"

        # Verify UtilityRoutes was instantiated with start_time
        mock_utility_routes_class.assert_called_once_with(start_time=mock_now)
        mock_utility_routes.get_health_routes.assert_called_once_with(
            config=mock_base_config,
            app_config=mock_app_config,
        )

        # Verify routers were added to app with correct prefix
        assert mock_fastapi_app.include_router.call_count == 3
        for call in mock_fastapi_app.include_router.call_args_list:
            assert call.kwargs["prefix"] == "/test-service/1.0.0"

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.os.path.exists")
    @patch("sk_agents.appv1.os.path.join")
    @patch("sk_agents.appv1.datetime")
    def test_run_with_custom_types_file_discovered(
        self,
        mock_datetime,
        mock_path_join,
        mock_path_exists,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run discovers custom_types.py when types_module is None."""
        config_file = "/path/to/agents/config.yaml"
        custom_types_path = "/path/to/agents/custom_types.py"

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: None,
        }.get(key)

        mock_path_join.return_value = custom_types_path
        mock_path_exists.return_value = True
        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        mock_path_join.assert_called_once_with("/path/to/agents", "custom_types.py")
        mock_path_exists.assert_called_once_with(custom_types_path)
        assert mock_app_config.props[TA_TYPES_MODULE.env_name] == custom_types_path
        mock_get_type_loader.assert_called_once_with(custom_types_path)

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.os.path.exists")
    @patch("sk_agents.appv1.os.path.join")
    @patch("sk_agents.appv1.datetime")
    def test_run_with_no_custom_types_file(
        self,
        mock_datetime,
        mock_path_join,
        mock_path_exists,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run when types_module is None and custom_types.py doesn't exist."""
        config_file = "/path/to/agents/config.yaml"
        custom_types_path = "/path/to/agents/custom_types.py"

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: None,
        }.get(key)

        mock_path_join.return_value = custom_types_path
        mock_path_exists.return_value = False
        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        mock_path_exists.assert_called_once_with(custom_types_path)
        # Should not set types_module in props
        assert TA_TYPES_MODULE.env_name not in mock_app_config.props
        mock_get_type_loader.assert_called_once_with(None)

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.datetime")
    def test_run_with_no_output_type(
        self,
        mock_datetime,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run when output_type is None."""
        config_file = "/path/to/agents/config.yaml"
        types_module = "/path/to/types.py"
        mock_base_config.output_type = None

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: types_module,
        }.get(key)

        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        mock_type_loader.get_type.assert_called_once_with("TestInput")
        # Verify output_class is Any
        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["output_class"] is Any

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.datetime")
    def test_run_with_no_description(
        self,
        mock_datetime,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run when description is None, uses default."""
        config_file = "/path/to/agents/config.yaml"
        types_module = "/path/to/types.py"
        mock_base_config.description = None

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: types_module,
        }.get(key)

        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["description"] == "test-service API"

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.datetime")
    def test_run_missing_input_type_raises_error(
        self,
        mock_datetime,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run raises ValueError when input_type is None."""
        config_file = "/path/to/agents/config.yaml"
        types_module = "/path/to/types.py"
        mock_base_config.input_type = None

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: types_module,
        }.get(key)

        mock_get_type_loader.return_value = mock_type_loader

        with pytest.raises(ValueError, match="Missing mandatory config property: input_type"):
            AppV1.run(
                name="test-service",
                version="1.0.0",
                app_config=mock_app_config,
                config=mock_base_config,
                app=mock_fastapi_app,
            )

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.datetime")
    def test_run_extracts_root_handler_from_apiversion(
        self,
        mock_datetime,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run correctly extracts root handler from apiVersion."""
        config_file = "/path/to/agents/config.yaml"
        types_module = "/path/to/types.py"
        mock_base_config.apiVersion = "tealagents/v1alpha1"

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: types_module,
        }.get(key)

        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["root_handler_name"] == "tealagents"

        ws_call = mock_routes_class.get_websocket_routes.call_args
        assert ws_call.kwargs["root_handler_name"] == "tealagents"

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.datetime")
    def test_run_uses_dirname_of_config_file(
        self,
        mock_datetime,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run extracts directory from config file path."""
        config_file = "/some/deep/path/to/agents/config.yaml"
        types_module = "/path/to/types.py"

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: types_module,
        }.get(key)

        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        expected_agents_path = os.path.dirname(config_file)
        mock_initialize_plugin_loader.assert_called_once_with(
            agents_path=expected_agents_path, app_config=mock_app_config
        )

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.datetime")
    def test_run_passes_input_class_to_routes(
        self,
        mock_datetime,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test run passes input_class to both REST and WebSocket routes."""
        config_file = "/path/to/agents/config.yaml"
        types_module = "/path/to/types.py"
        mock_input_class = MagicMock()
        mock_output_class = MagicMock()

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: types_module,
        }.get(key)

        mock_type_loader.get_type.side_effect = lambda x: {
            "TestInput": mock_input_class,
            "TestOutput": mock_output_class,
        }[x]

        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        rest_call = mock_routes_class.get_rest_routes.call_args
        assert rest_call.kwargs["input_class"] is mock_input_class
        assert rest_call.kwargs["output_class"] is mock_output_class

        ws_call = mock_routes_class.get_websocket_routes.call_args
        assert ws_call.kwargs["input_class"] is mock_input_class

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.os.path.exists")
    @patch("sk_agents.appv1.os.path.join")
    @patch("sk_agents.appv1.datetime")
    def test_run_custom_types_discovery_flow(
        self,
        mock_datetime,
        mock_path_join,
        mock_path_exists,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test the complete flow of custom types discovery."""
        config_file = "/my/agents/directory/config.yaml"
        agents_path = "/my/agents/directory"
        custom_types_path = "/my/agents/directory/custom_types.py"

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: None,
        }.get(key)

        mock_path_join.return_value = custom_types_path
        mock_path_exists.return_value = True
        mock_get_type_loader.return_value = mock_type_loader
        mock_routes_class.get_rest_routes.return_value = MagicMock()
        mock_routes_class.get_websocket_routes.return_value = MagicMock()

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="test-service",
            version="1.0.0",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        # Verify the complete flow
        # 1. Config file path extracted
        mock_app_config.get.assert_any_call(TA_SERVICE_CONFIG.env_name)
        # 2. Agents path derived from config file
        assert mock_path_join.call_args[0][0] == agents_path
        assert mock_path_join.call_args[0][1] == "custom_types.py"
        # 3. Check if custom_types.py exists
        mock_path_exists.assert_called_once_with(custom_types_path)
        # 4. Set custom types module in config
        assert mock_app_config.props[TA_TYPES_MODULE.env_name] == custom_types_path
        # 5. Type loader created with custom types
        mock_get_type_loader.assert_called_once_with(custom_types_path)

    @patch("sk_agents.appv1.UtilityRoutes")
    @patch("sk_agents.appv1.Routes")
    @patch("sk_agents.appv1.initialize_plugin_loader")
    @patch("sk_agents.appv1.get_type_loader")
    @patch("sk_agents.appv1.datetime")
    def test_run_router_prefix_format(
        self,
        mock_datetime,
        mock_get_type_loader,
        mock_initialize_plugin_loader,
        mock_routes_class,
        mock_utility_routes_class,
        mock_app_config,
        mock_base_config,
        mock_fastapi_app,
        mock_type_loader,
    ):
        """Test that routers are registered with correct prefix format."""
        config_file = "/path/to/agents/config.yaml"
        types_module = "/path/to/types.py"

        mock_app_config.get.side_effect = lambda key: {
            TA_SERVICE_CONFIG.env_name: config_file,
            TA_TYPES_MODULE.env_name: types_module,
        }.get(key)

        mock_get_type_loader.return_value = mock_type_loader
        mock_rest_router = MagicMock()
        mock_ws_router = MagicMock()
        mock_routes_class.get_rest_routes.return_value = mock_rest_router
        mock_routes_class.get_websocket_routes.return_value = mock_ws_router

        # Mock UtilityRoutes
        mock_utility_routes = MagicMock()
        mock_utility_routes.get_health_routes.return_value = MagicMock()
        mock_utility_routes_class.return_value = mock_utility_routes

        # Mock datetime.now
        mock_datetime.now.return_value = MagicMock()

        AppV1.run(
            name="my-agent",
            version="2.5.1",
            app_config=mock_app_config,
            config=mock_base_config,
            app=mock_fastapi_app,
        )

        assert mock_fastapi_app.include_router.call_count == 3
        call1 = mock_fastapi_app.include_router.call_args_list[0]
        call2 = mock_fastapi_app.include_router.call_args_list[1]

        # First call should be REST router
        assert call1[0][0] is mock_rest_router
        assert call1[1]["prefix"] == "/my-agent/2.5.1"

        # Second call should be WebSocket router
        assert call2[0][0] is mock_ws_router
        assert call2[1]["prefix"] == "/my-agent/2.5.1"
