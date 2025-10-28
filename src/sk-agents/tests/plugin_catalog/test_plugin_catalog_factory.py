"""Unit tests for PluginCatalogFactory."""

from unittest.mock import MagicMock, patch

import pytest

from sk_agents.plugin_catalog.plugin_catalog import PluginCatalog
from sk_agents.plugin_catalog.plugin_catalog_factory import PluginCatalogFactory


class TestPluginCatalogFactory:
    """Test suite for PluginCatalogFactory."""

    def setup_method(self):
        """Reset the singleton instance before each test."""
        # Clear the singleton instance
        if hasattr(PluginCatalogFactory, "_instances"):
            PluginCatalogFactory._instances.clear()

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    def test_singleton_pattern(self, mock_app_config_class):
        """Test that PluginCatalogFactory follows singleton pattern."""
        mock_app_config = MagicMock()
        mock_app_config_class.return_value = mock_app_config

        factory1 = PluginCatalogFactory()
        factory2 = PluginCatalogFactory()

        assert factory1 is factory2, "Should return the same instance"

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    def test_initialization(self, mock_app_config_class):
        """Test factory initialization sets up app_config correctly."""
        mock_app_config = MagicMock()
        mock_app_config_class.return_value = mock_app_config

        factory = PluginCatalogFactory()

        assert factory.app_config is mock_app_config
        assert factory._catalog_instance is None

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.ModuleLoader")
    def test_get_catalog_creates_instance(self, mock_module_loader, mock_app_config_class):
        """Test that get_catalog creates a catalog instance on first call."""
        # Setup mocks
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": "sk_agents.plugin_catalog.local_plugin_catalog",
            "TA_PLUGIN_CATALOG_CLASS": "MockPluginCatalog",
            "TA_PLUGIN_CATALOG_FILE": "test_catalog.json",
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        # Create a real class that inherits from PluginCatalog
        class MockPluginCatalog(PluginCatalog):
            def __init__(self, app_config):
                self.app_config = app_config

            def get_plugin(self, plugin_id: str):
                return None

            def get_tool(self, tool_id: str):
                return None

        # Mock the module loading
        mock_module = MagicMock()
        mock_module.MockPluginCatalog = MockPluginCatalog
        mock_module_loader.load_module.return_value = mock_module

        factory = PluginCatalogFactory()
        catalog = factory.get_catalog()

        assert isinstance(catalog, PluginCatalog)
        assert catalog.app_config is mock_app_config
        mock_module_loader.load_module.assert_called_once_with(
            "sk_agents.plugin_catalog.local_plugin_catalog"
        )

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.ModuleLoader")
    def test_get_catalog_returns_cached_instance(self, mock_module_loader, mock_app_config_class):
        """Test that get_catalog returns cached instance on subsequent calls."""
        # Setup mocks
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": "sk_agents.plugin_catalog.local_plugin_catalog",
            "TA_PLUGIN_CATALOG_CLASS": "MockPluginCatalog",
            "TA_PLUGIN_CATALOG_FILE": "test_catalog.json",
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        # Create a real class that inherits from PluginCatalog
        class MockPluginCatalog(PluginCatalog):
            def __init__(self, app_config):
                self.app_config = app_config

            def get_plugin(self, plugin_id: str):
                return None

            def get_tool(self, tool_id: str):
                return None

        # Mock the module loading
        mock_module = MagicMock()
        mock_module.MockPluginCatalog = MockPluginCatalog
        mock_module_loader.load_module.return_value = mock_module

        factory = PluginCatalogFactory()
        catalog1 = factory.get_catalog()
        catalog2 = factory.get_catalog()

        assert catalog1 is catalog2
        # Module loader should only be called once
        assert mock_module_loader.load_module.call_count == 1

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    def test_create_catalog_missing_module_name(self, mock_app_config_class):
        """Test that _create_catalog raises ValueError when module name is missing."""
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": None,
            "TA_PLUGIN_CATALOG_CLASS": "FileBasedPluginCatalog",
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        factory = PluginCatalogFactory()

        with pytest.raises(
            ValueError,
            match="Both TA_PLUGIN_CATALOG_MODULE and TA_PLUGIN_CATALOG_CLASS.*must be set",
        ):
            factory.get_catalog()

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    def test_create_catalog_missing_class_name(self, mock_app_config_class):
        """Test that _create_catalog raises ValueError when class name is missing."""
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": "sk_agents.plugin_catalog.local_plugin_catalog",
            "TA_PLUGIN_CATALOG_CLASS": None,
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        factory = PluginCatalogFactory()

        with pytest.raises(
            ValueError,
            match="Both TA_PLUGIN_CATALOG_MODULE and TA_PLUGIN_CATALOG_CLASS.*must be set",
        ):
            factory.get_catalog()

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    def test_create_catalog_missing_both(self, mock_app_config_class):
        """Test that _create_catalog raises ValueError when both are missing."""
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": "",
            "TA_PLUGIN_CATALOG_CLASS": "",
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        factory = PluginCatalogFactory()

        with pytest.raises(
            ValueError,
            match="Both TA_PLUGIN_CATALOG_MODULE and TA_PLUGIN_CATALOG_CLASS.*must be set",
        ):
            factory.get_catalog()

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.ModuleLoader")
    def test_create_catalog_import_error(self, mock_module_loader, mock_app_config_class):
        """Test that _create_catalog handles ImportError appropriately."""
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": "nonexistent.module",
            "TA_PLUGIN_CATALOG_CLASS": "SomeClass",
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        # Simulate import error
        mock_module_loader.load_module.side_effect = ImportError("Module not found")

        factory = PluginCatalogFactory()

        with pytest.raises(ImportError, match="Failed to import module 'nonexistent.module'"):
            factory.get_catalog()

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.ModuleLoader")
    def test_create_catalog_attribute_error(self, mock_module_loader, mock_app_config_class):
        """Test that _create_catalog handles AttributeError when class not found."""
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": "sk_agents.plugin_catalog.local_plugin_catalog",
            "TA_PLUGIN_CATALOG_CLASS": "NonExistentClass",
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        # Mock module without the requested class
        mock_module = MagicMock(spec=[])  # Empty spec means no attributes
        mock_module_loader.load_module.return_value = mock_module

        factory = PluginCatalogFactory()

        with pytest.raises(
            AttributeError,
            match="Class 'NonExistentClass' not found in module.*local_plugin_catalog",
        ):
            factory.get_catalog()

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.ModuleLoader")
    def test_create_catalog_not_subclass_of_plugin_catalog(
        self, mock_module_loader, mock_app_config_class
    ):
        """Test that _create_catalog raises TypeError when class doesn't inherit
        from PluginCatalog."""
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": "some.module",
            "TA_PLUGIN_CATALOG_CLASS": "InvalidClass",
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        # Mock module with a class that doesn't inherit from PluginCatalog
        mock_module = MagicMock()

        class InvalidClass:
            pass

        mock_module.InvalidClass = InvalidClass
        mock_module_loader.load_module.return_value = mock_module

        factory = PluginCatalogFactory()

        with pytest.raises(
            TypeError,
            match="Class InvalidClass in module some.module must inherit from PluginCatalog",
        ):
            factory.get_catalog()

    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.AppConfig")
    @patch("sk_agents.plugin_catalog.plugin_catalog_factory.ModuleLoader")
    def test_create_catalog_successful_instantiation(
        self, mock_module_loader, mock_app_config_class
    ):
        """Test successful catalog instantiation with valid class."""
        mock_app_config = MagicMock()
        mock_app_config.get.side_effect = lambda key: {
            "TA_PLUGIN_CATALOG_MODULE": "sk_agents.plugin_catalog.local_plugin_catalog",
            "TA_PLUGIN_CATALOG_CLASS": "FileBasedPluginCatalog",
            "TA_PLUGIN_CATALOG_FILE": "catalog.json",
        }.get(key)
        mock_app_config_class.return_value = mock_app_config

        # Create a proper mock class that inherits from PluginCatalog
        class MockPluginCatalog(PluginCatalog):
            def __init__(self, app_config):
                self.app_config = app_config

            def get_plugin(self, plugin_id: str):
                return None

            def get_tool(self, tool_id: str):
                return None

        mock_module = MagicMock()
        mock_module.FileBasedPluginCatalog = MockPluginCatalog
        mock_module_loader.load_module.return_value = mock_module

        factory = PluginCatalogFactory()
        catalog = factory.get_catalog()

        assert isinstance(catalog, PluginCatalog)
        assert catalog.app_config is mock_app_config
