from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError
from semantic_kernel import Kernel
from ska_utils import AppConfig

from sk_agents.configs import TA_REMOTE_PLUGIN_PATH
from sk_agents.tealagents.remote_plugin_loader import (
    RemotePlugin,
    RemotePluginCatalog,
    RemotePluginLoader,
    RemotePlugins,
)


@pytest.fixture
def mock_app_config_with_path():
    """Create a mock app config with remote plugin path."""
    config = MagicMock(spec=AppConfig)
    config.get.return_value = "/path/to/plugins.yaml"
    return config


@pytest.fixture
def mock_app_config_no_path():
    """Create a mock app config without remote plugin path."""
    config = MagicMock(spec=AppConfig)
    config.get.return_value = None
    return config


@pytest.fixture
def sample_remote_plugin():
    """Create a sample RemotePlugin."""
    return RemotePlugin(
        plugin_name="test_plugin",
        openapi_json_path="/path/to/openapi.json",
        server_url="https://api.example.com",
    )


@pytest.fixture
def sample_remote_plugins(sample_remote_plugin):
    """Create a sample RemotePlugins collection."""
    return RemotePlugins(remote_plugins=[sample_remote_plugin])


class TestRemotePlugin:
    """Test RemotePlugin model."""

    def test_create_remote_plugin_with_server_url(self):
        """Test creating RemotePlugin with all fields."""
        plugin = RemotePlugin(
            plugin_name="test_plugin",
            openapi_json_path="/path/to/openapi.json",
            server_url="https://api.example.com",
        )

        assert plugin.plugin_name == "test_plugin"
        assert plugin.openapi_json_path == "/path/to/openapi.json"
        assert plugin.server_url == "https://api.example.com"

    def test_create_remote_plugin_without_server_url(self):
        """Test creating RemotePlugin without server_url (optional field)."""
        plugin = RemotePlugin(
            plugin_name="test_plugin",
            openapi_json_path="/path/to/openapi.json",
        )

        assert plugin.plugin_name == "test_plugin"
        assert plugin.openapi_json_path == "/path/to/openapi.json"
        assert plugin.server_url is None

    def test_remote_plugin_validation_missing_required_field(self):
        """Test that RemotePlugin validation fails without required fields."""
        with pytest.raises(ValidationError):
            RemotePlugin(plugin_name="test_plugin")  # Missing openapi_json_path


class TestRemotePlugins:
    """Test RemotePlugins model."""

    def test_create_remote_plugins_empty(self):
        """Test creating RemotePlugins with empty list."""
        plugins = RemotePlugins(remote_plugins=[])
        assert plugins.remote_plugins == []

    def test_create_remote_plugins_with_plugins(self, sample_remote_plugin):
        """Test creating RemotePlugins with plugins."""
        plugin2 = RemotePlugin(
            plugin_name="plugin2",
            openapi_json_path="/path/to/openapi2.json",
        )
        plugins = RemotePlugins(remote_plugins=[sample_remote_plugin, plugin2])

        assert len(plugins.remote_plugins) == 2
        assert plugins.remote_plugins[0].plugin_name == "test_plugin"
        assert plugins.remote_plugins[1].plugin_name == "plugin2"

    def test_get_existing_plugin(self, sample_remote_plugins):
        """Test getting an existing plugin by name."""
        result = sample_remote_plugins.get("test_plugin")

        assert result is not None
        assert result.plugin_name == "test_plugin"
        assert result.openapi_json_path == "/path/to/openapi.json"

    def test_get_non_existing_plugin(self, sample_remote_plugins):
        """Test getting a non-existing plugin returns None."""
        result = sample_remote_plugins.get("non_existing_plugin")
        assert result is None

    def test_get_from_empty_list(self):
        """Test getting plugin from empty RemotePlugins."""
        plugins = RemotePlugins(remote_plugins=[])
        result = plugins.get("any_plugin")
        assert result is None

    def test_get_multiple_plugins(self):
        """Test getting specific plugin from multiple plugins."""
        plugin1 = RemotePlugin(
            plugin_name="plugin1",
            openapi_json_path="/path/1.json",
        )
        plugin2 = RemotePlugin(
            plugin_name="plugin2",
            openapi_json_path="/path/2.json",
        )
        plugin3 = RemotePlugin(
            plugin_name="plugin3",
            openapi_json_path="/path/3.json",
        )
        plugins = RemotePlugins(remote_plugins=[plugin1, plugin2, plugin3])

        result = plugins.get("plugin2")
        assert result is not None
        assert result.plugin_name == "plugin2"
        assert result.openapi_json_path == "/path/2.json"


class TestRemotePluginCatalog:
    """Test RemotePluginCatalog class."""

    @patch("sk_agents.tealagents.remote_plugin_loader.parse_yaml_file_as")
    def test_init_with_plugin_path(self, mock_parse_yaml, mock_app_config_with_path):
        """Test initialization with plugin path."""
        mock_remote_plugins = MagicMock(spec=RemotePlugins)
        mock_parse_yaml.return_value = mock_remote_plugins

        catalog = RemotePluginCatalog(mock_app_config_with_path)

        assert catalog.catalog is mock_remote_plugins
        mock_app_config_with_path.get.assert_called_once_with(TA_REMOTE_PLUGIN_PATH.env_name)
        mock_parse_yaml.assert_called_once_with(RemotePlugins, "/path/to/plugins.yaml")

    def test_init_without_plugin_path(self, mock_app_config_no_path):
        """Test initialization without plugin path."""
        catalog = RemotePluginCatalog(mock_app_config_no_path)

        assert catalog.catalog is None
        mock_app_config_no_path.get.assert_called_once_with(TA_REMOTE_PLUGIN_PATH.env_name)

    @patch("sk_agents.tealagents.remote_plugin_loader.parse_yaml_file_as")
    def test_get_remote_plugin_success(self, mock_parse_yaml, mock_app_config_with_path):
        """Test getting remote plugin successfully."""
        sample_plugin = RemotePlugin(
            plugin_name="test_plugin",
            openapi_json_path="/path/to/openapi.json",
        )
        mock_remote_plugins = MagicMock(spec=RemotePlugins)
        mock_remote_plugins.get.return_value = sample_plugin
        mock_parse_yaml.return_value = mock_remote_plugins

        catalog = RemotePluginCatalog(mock_app_config_with_path)
        result = catalog.get_remote_plugin("test_plugin")

        assert result is sample_plugin
        mock_remote_plugins.get.assert_called_once_with("test_plugin")

    @patch("sk_agents.tealagents.remote_plugin_loader.parse_yaml_file_as")
    def test_get_remote_plugin_not_found(self, mock_parse_yaml, mock_app_config_with_path):
        """Test getting remote plugin that doesn't exist."""
        mock_remote_plugins = MagicMock(spec=RemotePlugins)
        mock_remote_plugins.get.return_value = None
        mock_parse_yaml.return_value = mock_remote_plugins

        catalog = RemotePluginCatalog(mock_app_config_with_path)
        result = catalog.get_remote_plugin("non_existing_plugin")

        assert result is None
        mock_remote_plugins.get.assert_called_once_with("non_existing_plugin")

    @patch("sk_agents.tealagents.remote_plugin_loader.parse_yaml_file_as")
    def test_get_remote_plugin_exception_handling(self, mock_parse_yaml, mock_app_config_with_path):
        """Test exception handling in get_remote_plugin."""
        mock_remote_plugins = MagicMock(spec=RemotePlugins)
        mock_remote_plugins.get.side_effect = Exception("Catalog error")
        mock_parse_yaml.return_value = mock_remote_plugins

        catalog = RemotePluginCatalog(mock_app_config_with_path)

        with pytest.raises(Exception, match="Catalog error"):
            catalog.get_remote_plugin("test_plugin")

    @patch("sk_agents.tealagents.remote_plugin_loader.parse_yaml_file_as")
    def test_get_remote_plugin_logs_exception(self, mock_parse_yaml, mock_app_config_with_path):
        """Test that get_remote_plugin logs exceptions."""
        mock_remote_plugins = MagicMock(spec=RemotePlugins)
        mock_remote_plugins.get.side_effect = ValueError("Test error")
        mock_parse_yaml.return_value = mock_remote_plugins

        catalog = RemotePluginCatalog(mock_app_config_with_path)

        with patch.object(catalog.logger, "exception") as mock_log:
            with pytest.raises(ValueError):
                catalog.get_remote_plugin("test_plugin")

            mock_log.assert_called_once()
            assert "could not get remote pluging test_plugin" in str(mock_log.call_args)


class TestRemotePluginLoader:
    """Test RemotePluginLoader class."""

    @pytest.fixture
    def mock_catalog(self):
        """Create a mock RemotePluginCatalog."""
        catalog = MagicMock(spec=RemotePluginCatalog)
        return catalog

    @pytest.fixture
    def loader(self, mock_catalog):
        """Create a RemotePluginLoader instance."""
        return RemotePluginLoader(mock_catalog)

    def test_init(self, mock_catalog):
        """Test RemotePluginLoader initialization."""
        loader = RemotePluginLoader(mock_catalog)
        assert loader.catalog is mock_catalog

    @patch("sk_agents.tealagents.remote_plugin_loader.OpenAPIFunctionExecutionParameters")
    @patch("sk_agents.tealagents.remote_plugin_loader.Kernel.add_plugin_from_openapi")
    @patch("sk_agents.tealagents.remote_plugin_loader.httpx.AsyncClient")
    def test_load_remote_plugins_single_plugin(
        self, mock_async_client_class, mock_add_plugin, mock_exec_params, loader
    ):
        """Test loading a single remote plugin."""
        kernel = Kernel()
        mock_client = MagicMock()
        mock_async_client_class.return_value = mock_client
        mock_execution_settings = MagicMock()
        mock_exec_params.return_value = mock_execution_settings

        remote_plugin = RemotePlugin(
            plugin_name="test_plugin",
            openapi_json_path="/path/to/openapi.json",
            server_url="https://api.example.com",
        )
        loader.catalog.get_remote_plugin.return_value = remote_plugin

        loader.load_remote_plugins(kernel, ["test_plugin"])

        loader.catalog.get_remote_plugin.assert_called_once_with("test_plugin")
        mock_async_client_class.assert_called_once()

        # Verify OpenAPIFunctionExecutionParameters was called with correct args
        mock_exec_params.assert_called_once_with(
            http_client=mock_client,
            server_url_override="https://api.example.com",
            enable_payload_namespacing=True,
        )

        # Verify add_plugin_from_openapi was called
        mock_add_plugin.assert_called_once_with(
            plugin_name="test_plugin",
            openapi_document_path="/path/to/openapi.json",
            execution_settings=mock_execution_settings,
        )

    @patch("sk_agents.tealagents.remote_plugin_loader.OpenAPIFunctionExecutionParameters")
    @patch("sk_agents.tealagents.remote_plugin_loader.Kernel.add_plugin_from_openapi")
    @patch("sk_agents.tealagents.remote_plugin_loader.httpx.AsyncClient")
    def test_load_remote_plugins_without_server_url(
        self, mock_async_client_class, mock_add_plugin, mock_exec_params, loader
    ):
        """Test loading remote plugin without server_url."""
        kernel = Kernel()
        mock_client = MagicMock()
        mock_async_client_class.return_value = mock_client
        mock_execution_settings = MagicMock()
        mock_exec_params.return_value = mock_execution_settings

        remote_plugin = RemotePlugin(
            plugin_name="test_plugin",
            openapi_json_path="/path/to/openapi.json",
        )
        loader.catalog.get_remote_plugin.return_value = remote_plugin

        loader.load_remote_plugins(kernel, ["test_plugin"])

        # Verify server_url_override is None
        mock_exec_params.assert_called_once_with(
            http_client=mock_client,
            server_url_override=None,
            enable_payload_namespacing=True,
        )

    @patch("sk_agents.tealagents.remote_plugin_loader.OpenAPIFunctionExecutionParameters")
    @patch("sk_agents.tealagents.remote_plugin_loader.Kernel.add_plugin_from_openapi")
    @patch("sk_agents.tealagents.remote_plugin_loader.httpx.AsyncClient")
    def test_load_remote_plugins_multiple_plugins(
        self, mock_async_client_class, mock_add_plugin, mock_exec_params, loader
    ):
        """Test loading multiple remote plugins."""
        kernel = Kernel()
        mock_client = MagicMock()
        mock_async_client_class.return_value = mock_client
        mock_execution_settings = MagicMock()
        mock_exec_params.return_value = mock_execution_settings

        plugin1 = RemotePlugin(
            plugin_name="plugin1",
            openapi_json_path="/path/1.json",
            server_url="https://api1.example.com",
        )
        plugin2 = RemotePlugin(
            plugin_name="plugin2",
            openapi_json_path="/path/2.json",
            server_url="https://api2.example.com",
        )

        loader.catalog.get_remote_plugin.side_effect = [plugin1, plugin2]

        loader.load_remote_plugins(kernel, ["plugin1", "plugin2"])

        assert loader.catalog.get_remote_plugin.call_count == 2
        assert mock_async_client_class.call_count == 2
        assert mock_add_plugin.call_count == 2
        assert mock_exec_params.call_count == 2

    def test_load_remote_plugins_plugin_not_found(self, loader):
        """Test loading remote plugin that doesn't exist in catalog."""
        kernel = Kernel()
        loader.catalog.get_remote_plugin.return_value = None

        with pytest.raises(ValueError, match="Remote plugin non_existing not found in catalog"):
            loader.load_remote_plugins(kernel, ["non_existing"])

    def test_load_remote_plugins_empty_list(self, loader):
        """Test loading remote plugins with empty list."""
        kernel = Kernel()

        # Should not raise any errors
        loader.load_remote_plugins(kernel, [])

        loader.catalog.get_remote_plugin.assert_not_called()

    @patch("sk_agents.tealagents.remote_plugin_loader.OpenAPIFunctionExecutionParameters")
    @patch("sk_agents.tealagents.remote_plugin_loader.Kernel.add_plugin_from_openapi")
    @patch("sk_agents.tealagents.remote_plugin_loader.httpx.Timeout")
    @patch("sk_agents.tealagents.remote_plugin_loader.httpx.AsyncClient")
    def test_load_remote_plugins_httpx_timeout_configuration(
        self, mock_async_client_class, mock_timeout, mock_add_plugin, mock_exec_params, loader
    ):
        """Test that httpx.AsyncClient is configured with correct timeout."""
        kernel = Kernel()
        mock_client = MagicMock()
        mock_async_client_class.return_value = mock_client
        mock_timeout_obj = MagicMock()
        mock_timeout.return_value = mock_timeout_obj
        mock_execution_settings = MagicMock()
        mock_exec_params.return_value = mock_execution_settings

        remote_plugin = RemotePlugin(
            plugin_name="test_plugin",
            openapi_json_path="/path/to/openapi.json",
        )
        loader.catalog.get_remote_plugin.return_value = remote_plugin

        loader.load_remote_plugins(kernel, ["test_plugin"])

        # Verify Timeout was called with 60.0
        mock_timeout.assert_called_once_with(60.0)
        # Verify AsyncClient was called with the timeout
        mock_async_client_class.assert_called_once_with(timeout=mock_timeout_obj)

    @patch("sk_agents.tealagents.remote_plugin_loader.OpenAPIFunctionExecutionParameters")
    @patch("sk_agents.tealagents.remote_plugin_loader.Kernel.add_plugin_from_openapi")
    @patch("sk_agents.tealagents.remote_plugin_loader.httpx.AsyncClient")
    def test_load_remote_plugins_first_found_second_not_found(
        self, mock_async_client_class, mock_add_plugin, mock_exec_params, loader
    ):
        """Test loading plugins where first is found but second is not."""
        kernel = Kernel()
        mock_client = MagicMock()
        mock_async_client_class.return_value = mock_client
        mock_execution_settings = MagicMock()
        mock_exec_params.return_value = mock_execution_settings

        plugin1 = RemotePlugin(
            plugin_name="plugin1",
            openapi_json_path="/path/1.json",
        )

        loader.catalog.get_remote_plugin.side_effect = [plugin1, None]

        with pytest.raises(ValueError, match="Remote plugin plugin2 not found in catalog"):
            loader.load_remote_plugins(kernel, ["plugin1", "plugin2"])

        # First plugin should have been added before error
        assert mock_add_plugin.call_count == 1


class TestIntegration:
    """Integration tests combining multiple components."""

    @patch("sk_agents.tealagents.remote_plugin_loader.OpenAPIFunctionExecutionParameters")
    @patch("sk_agents.tealagents.remote_plugin_loader.Kernel.add_plugin_from_openapi")
    @patch("sk_agents.tealagents.remote_plugin_loader.parse_yaml_file_as")
    @patch("sk_agents.tealagents.remote_plugin_loader.httpx.AsyncClient")
    def test_end_to_end_plugin_loading(
        self,
        mock_async_client_class,
        mock_parse_yaml,
        mock_add_plugin,
        mock_exec_params,
        mock_app_config_with_path,
    ):
        """Test end-to-end plugin loading from catalog to kernel."""
        # Setup
        kernel = Kernel()
        mock_client = MagicMock()
        mock_async_client_class.return_value = mock_client
        mock_execution_settings = MagicMock()
        mock_exec_params.return_value = mock_execution_settings

        plugin1 = RemotePlugin(
            plugin_name="weather",
            openapi_json_path="/plugins/weather.json",
            server_url="https://weather.api.com",
        )
        plugin2 = RemotePlugin(
            plugin_name="search",
            openapi_json_path="/plugins/search.json",
        )

        remote_plugins_collection = RemotePlugins(remote_plugins=[plugin1, plugin2])
        mock_parse_yaml.return_value = remote_plugins_collection

        # Create catalog and loader
        catalog = RemotePluginCatalog(mock_app_config_with_path)
        loader = RemotePluginLoader(catalog)

        # Load plugins
        loader.load_remote_plugins(kernel, ["weather", "search"])

        assert mock_add_plugin.call_count == 2
        assert mock_exec_params.call_count == 2

        # Verify first plugin call to add_plugin_from_openapi
        first_call = mock_add_plugin.call_args_list[0].kwargs
        assert first_call["plugin_name"] == "weather"
        assert first_call["openapi_document_path"] == "/plugins/weather.json"
        assert first_call["execution_settings"] is mock_execution_settings

        # Verify second plugin call to add_plugin_from_openapi
        second_call = mock_add_plugin.call_args_list[1].kwargs
        assert second_call["plugin_name"] == "search"
        assert second_call["openapi_document_path"] == "/plugins/search.json"
        assert second_call["execution_settings"] is mock_execution_settings

        # Verify OpenAPIFunctionExecutionParameters calls
        first_params_call = mock_exec_params.call_args_list[0].kwargs
        assert first_params_call["server_url_override"] == "https://weather.api.com"
        assert first_params_call["http_client"] is mock_client

        second_params_call = mock_exec_params.call_args_list[1].kwargs
        assert second_params_call["server_url_override"] is None
        assert second_params_call["http_client"] is mock_client

    @patch("sk_agents.tealagents.remote_plugin_loader.parse_yaml_file_as")
    def test_catalog_with_no_path_loader_behavior(self, mock_parse_yaml, mock_app_config_no_path):
        """Test behavior when catalog has no plugin path configured."""
        catalog = RemotePluginCatalog(mock_app_config_no_path)
        loader = RemotePluginLoader(catalog)
        kernel = Kernel()

        # Catalog has no path, so catalog is None, get should fail
        with pytest.raises(AttributeError):
            loader.load_remote_plugins(kernel, ["any_plugin"])
