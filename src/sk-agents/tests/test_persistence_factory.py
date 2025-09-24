"""Tests for PersistenceFactory including in-memory and custom implementations."""

from unittest.mock import MagicMock, patch

import pytest

from sk_agents.configs import TA_PERSISTENCE_CLASS, TA_PERSISTENCE_MODULE
from sk_agents.persistence.in_memory_persistence_manager import InMemoryPersistenceManager
from sk_agents.persistence.persistence_factory import PersistenceFactory
from sk_agents.persistence.task_persistence_manager import TaskPersistenceManager


# Clear the Singleton cache before each test
@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset Singleton before each test."""
    PersistenceFactory._instances = {}
    yield
    PersistenceFactory._instances = {}


@pytest.fixture
def mock_app_config():
    """Create a mock app config for testing."""
    return MagicMock()


class TestPersistenceFactoryBasics:
    """Test basic factory functionality."""

    def test_default_behavior(self, mock_app_config):
        """Test that factory defaults to InMemoryPersistenceManager when no custom config."""
        # Mock default values (indicating no custom config)
        mock_app_config.get.side_effect = lambda key: {
            TA_PERSISTENCE_MODULE.env_name: TA_PERSISTENCE_MODULE.default_value,
            TA_PERSISTENCE_CLASS.env_name: TA_PERSISTENCE_CLASS.default_value,
        }.get(key)

        factory = PersistenceFactory(mock_app_config)
        manager = factory.get_persistence_manager()

        assert isinstance(manager, InMemoryPersistenceManager)
        assert factory.module is None
        assert factory.class_name is None

    @patch("sk_agents.persistence.persistence_factory.ModuleLoader.load_module")
    def test_custom_implementation_success(self, mock_load_module, mock_app_config):
        """Test successful loading of custom persistence implementation."""
        mock_app_config.get.side_effect = lambda key: {
            TA_PERSISTENCE_MODULE.env_name: "custom_module",
            TA_PERSISTENCE_CLASS.env_name: "CustomPersistenceManager",
        }.get(key)

        # Create a mock custom class that inherits from TaskPersistenceManager
        class MockCustomPersistenceManager(TaskPersistenceManager):
            async def create(self, task):
                pass

            async def load(self, task_id):
                pass

            async def update(self, task):
                pass

            async def delete(self, task_id):
                pass

            async def load_by_request_id(self, request_id):
                pass

        dummy_module = MagicMock()
        dummy_module.CustomPersistenceManager = MockCustomPersistenceManager
        dummy_module.__name__ = "custom_module"
        mock_load_module.return_value = dummy_module

        factory = PersistenceFactory(mock_app_config)
        manager = factory.get_persistence_manager()

        assert isinstance(manager, MockCustomPersistenceManager)
        mock_load_module.assert_called_once_with("custom_module")

    @patch("sk_agents.persistence.persistence_factory.ModuleLoader.load_module")
    def test_module_load_failure(self, mock_load_module, mock_app_config):
        """Test handling of module loading failures."""
        mock_app_config.get.side_effect = lambda key: {
            TA_PERSISTENCE_MODULE.env_name: "non_existent_module",
            TA_PERSISTENCE_CLASS.env_name: "CustomPersistenceManager",
        }.get(key)

        mock_load_module.side_effect = ImportError("Module not found")

        with pytest.raises(ImportError, match="Failed to load module 'non_existent_module'"):
            PersistenceFactory(mock_app_config)

    @patch("sk_agents.persistence.persistence_factory.ModuleLoader.load_module")
    def test_class_not_found(self, mock_load_module, mock_app_config):
        """Test handling when specified class doesn't exist in module."""
        mock_app_config.get.side_effect = lambda key: {
            TA_PERSISTENCE_MODULE.env_name: "valid_module",
            TA_PERSISTENCE_CLASS.env_name: "NonExistentClass",
        }.get(key)

        dummy_module = MagicMock()
        dummy_module.__name__ = "valid_module"
        # Don't add NonExistentClass to the module
        del dummy_module.NonExistentClass  # This will raise AttributeError when accessed
        mock_load_module.return_value = dummy_module

        with pytest.raises(
            ValueError, match="Custom Task Persistence Manager class: NonExistentClass"
        ):
            PersistenceFactory(mock_app_config)

    @patch("sk_agents.persistence.persistence_factory.ModuleLoader.load_module")
    def test_class_wrong_type(self, mock_load_module, mock_app_config):
        """Test handling when class doesn't inherit from TaskPersistenceManager."""
        mock_app_config.get.side_effect = lambda key: {
            TA_PERSISTENCE_MODULE.env_name: "valid_module",
            TA_PERSISTENCE_CLASS.env_name: "WrongTypeClass",
        }.get(key)

        class WrongTypeClass:
            """A class that doesn't inherit from TaskPersistenceManager."""

            pass

        dummy_module = MagicMock()
        dummy_module.WrongTypeClass = WrongTypeClass
        dummy_module.__name__ = "valid_module"
        mock_load_module.return_value = dummy_module

        with pytest.raises(
            TypeError, match="Class 'WrongTypeClass' is not a subclass of TaskPersistenceManager"
        ):
            PersistenceFactory(mock_app_config)

    def test_singleton_behavior(self, mock_app_config):
        """Test that PersistenceFactory follows singleton pattern."""
        mock_app_config.get.side_effect = lambda key: {
            TA_PERSISTENCE_MODULE.env_name: TA_PERSISTENCE_MODULE.default_value,
            TA_PERSISTENCE_CLASS.env_name: TA_PERSISTENCE_CLASS.default_value,
        }.get(key)

        factory1 = PersistenceFactory(mock_app_config)
        factory2 = PersistenceFactory(mock_app_config)

        assert factory1 is factory2

    @patch("sk_agents.persistence.persistence_factory.ModuleLoader.load_module")
    def test_custom_manager_with_app_config(self, mock_load_module, mock_app_config):
        """Test that custom manager can be initialized with app_config."""
        mock_app_config.get.side_effect = lambda key: {
            TA_PERSISTENCE_MODULE.env_name: "custom_module",
            TA_PERSISTENCE_CLASS.env_name: "CustomPersistenceManager",
        }.get(key)

        # Create a mock custom class that accepts app_config
        class MockCustomPersistenceManager(TaskPersistenceManager):
            def __init__(self, app_config=None):
                self.app_config = app_config

            async def create(self, task):
                pass

            async def load(self, task_id):
                pass

            async def update(self, task):
                pass

            async def delete(self, task_id):
                pass

            async def load_by_request_id(self, request_id):
                pass

        dummy_module = MagicMock()
        dummy_module.CustomPersistenceManager = MockCustomPersistenceManager
        dummy_module.__name__ = "custom_module"
        mock_load_module.return_value = dummy_module

        factory = PersistenceFactory(mock_app_config)
        manager = factory.get_persistence_manager()

        assert isinstance(manager, MockCustomPersistenceManager)
        assert manager.app_config == mock_app_config

    @patch("sk_agents.persistence.persistence_factory.ModuleLoader.load_module")
    def test_custom_manager_without_app_config(self, mock_load_module, mock_app_config):
        """Test that custom manager falls back when app_config not accepted."""
        mock_app_config.get.side_effect = lambda key: {
            TA_PERSISTENCE_MODULE.env_name: "custom_module",
            TA_PERSISTENCE_CLASS.env_name: "CustomPersistenceManager",
        }.get(key)

        # Create a mock custom class that doesn't accept app_config
        class MockCustomPersistenceManager(TaskPersistenceManager):
            def __init__(self):
                self.initialized = True

            async def create(self, task):
                pass

            async def load(self, task_id):
                pass

            async def update(self, task):
                pass

            async def delete(self, task_id):
                pass

            async def load_by_request_id(self, request_id):
                pass

        dummy_module = MagicMock()
        dummy_module.CustomPersistenceManager = MockCustomPersistenceManager
        dummy_module.__name__ = "custom_module"
        mock_load_module.return_value = dummy_module

        factory = PersistenceFactory(mock_app_config)
        manager = factory.get_persistence_manager()

        assert isinstance(manager, MockCustomPersistenceManager)
        assert manager.initialized is True
