import json
from unittest.mock import Mock, mock_open, patch

import pytest
from ska_utils import AppConfig

from sk_agents.exceptions import PluginCatalogDefinitionException, PluginFileReadException
from sk_agents.plugin_catalog.local_plugin_catalog import FileBasedPluginCatalog


class TestFileBasedPluginCatalog:
    @pytest.fixture
    def mock_app_config(self):
        config = Mock(spec=AppConfig)
        config.get.return_value = "/path/to/catalog.json"
        return config

    @pytest.fixture
    def sample_catalog_data(self):
        return {
            "plugins": [
                {
                    "plugin_id": "test_plugin_1",
                    "name": "Test Plugin 1",
                    "description": "A test plugin",
                    "version": "1.0.0",
                    "owner": "test_owner_1",
                    "plugin_type": {"type_name": "code"},
                    "tools": [
                        {
                            "tool_id": "tool_1",
                            "name": "Test Tool 1",
                            "description": "A test tool",
                            "governance": {
                                "requires_hitl": False,
                                "cost": "low",
                                "data_sensitivity": "public",
                            },
                            "auth": None,
                        }
                    ],
                },
                {
                    "plugin_id": "test_plugin_2",
                    "name": "Test Plugin 2",
                    "description": "Another test plugin",
                    "version": "1.0.0",
                    "owner": "test_owner_2",
                    "plugin_type": {"type_name": "code"},
                    "tools": [
                        {
                            "tool_id": "tool_2",
                            "name": "Test Tool 2",
                            "description": "Another test tool",
                            "governance": {
                                "requires_hitl": False,
                                "cost": "medium",
                                "data_sensitivity": "proprietary",
                            },
                            "auth": {
                                "auth_type": "oauth2",
                                "auth_server": "https://example.com/oauth",
                                "scopes": ["read", "write"],
                            },
                        }
                    ],
                },
            ]
        }

    def test_load_plugins_success(self, mock_app_config, sample_catalog_data):
        """Test successful loading and parsing of catalog file."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(sample_catalog_data))),
        ):
            catalog = FileBasedPluginCatalog(mock_app_config)

            # Verify plugins were loaded
            assert len(catalog._plugins) == 2
            assert len(catalog._tools) == 2

            # Verify plugin data
            plugin1 = catalog._plugins["test_plugin_1"]
            assert plugin1.plugin_id == "test_plugin_1"
            assert plugin1.name == "Test Plugin 1"

            plugin2 = catalog._plugins["test_plugin_2"]
            assert plugin2.plugin_id == "test_plugin_2"
            assert plugin2.name == "Test Plugin 2"

            # Verify tool indexing
            tool1 = catalog._tools["tool_1"]
            assert tool1.tool_id == "tool_1"
            assert tool1.name == "Test Tool 1"

            tool2 = catalog._tools["tool_2"]
            assert tool2.tool_id == "tool_2"
            assert tool2.name == "Test Tool 2"

    def test_get_plugin_existing(self, mock_app_config, sample_catalog_data):
        """Test retrieving an existing plugin."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(sample_catalog_data))),
        ):
            catalog = FileBasedPluginCatalog(mock_app_config)
            plugin = catalog.get_plugin("test_plugin_1")

            assert plugin is not None
            assert plugin.plugin_id == "test_plugin_1"
            assert plugin.name == "Test Plugin 1"

    def test_get_plugin_non_existing(self, mock_app_config, sample_catalog_data):
        """Test retrieving a non-existing plugin returns None."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(sample_catalog_data))),
        ):
            catalog = FileBasedPluginCatalog(mock_app_config)
            plugin = catalog.get_plugin("non_existing_plugin")

            assert plugin is None

    def test_get_tool_existing(self, mock_app_config, sample_catalog_data):
        """Test retrieving an existing tool."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(sample_catalog_data))),
        ):
            catalog = FileBasedPluginCatalog(mock_app_config)
            tool = catalog.get_tool("tool_1")

            assert tool is not None
            assert tool.tool_id == "tool_1"
            assert tool.name == "Test Tool 1"

    def test_get_tool_non_existing(self, mock_app_config, sample_catalog_data):
        """Test retrieving a non-existing tool returns None."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(sample_catalog_data))),
        ):
            catalog = FileBasedPluginCatalog(mock_app_config)
            tool = catalog.get_tool("non_existing_tool")

            assert tool is None

    def test_catalog_file_does_not_exist(self, mock_app_config):
        """Test handling when catalog file doesn't exist."""
        with patch("pathlib.Path.exists", return_value=False):
            catalog = FileBasedPluginCatalog(mock_app_config)

            assert len(catalog._plugins) == 0
            assert len(catalog._tools) == 0

    def test_invalid_json_format(self, mock_app_config):
        """Test handling of invalid JSON format."""
        invalid_json = "{ invalid json }"

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=invalid_json)),
        ):
            with pytest.raises(PluginFileReadException):
                FileBasedPluginCatalog(mock_app_config)

    def test_validation_error(self, mock_app_config):
        """Test handling of validation errors in plugin data."""
        invalid_catalog_data = {
            "plugins": [
                {
                    # Missing required fields
                    "plugin_id": "test_plugin"
                }
            ]
        }

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(invalid_catalog_data))),
        ):
            with pytest.raises(PluginCatalogDefinitionException):
                FileBasedPluginCatalog(mock_app_config)

    def test_file_read_error(self, mock_app_config):
        """Test handling of file read errors."""
        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", side_effect=OSError("File read error")),
        ):
            with pytest.raises(PluginFileReadException):
                FileBasedPluginCatalog(mock_app_config)

    def test_empty_catalog(self, mock_app_config):
        """Test handling of empty catalog."""
        empty_catalog_data = {"plugins": []}

        with (
            patch("pathlib.Path.exists", return_value=True),
            patch("builtins.open", mock_open(read_data=json.dumps(empty_catalog_data))),
        ):
            catalog = FileBasedPluginCatalog(mock_app_config)

            assert len(catalog._plugins) == 0
            assert len(catalog._tools) == 0
