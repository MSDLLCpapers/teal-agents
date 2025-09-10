from unittest.mock import MagicMock, patch

import pytest

from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.in_memory_secure_auth_storage_manager import (
    InMemorySecureAuthStorageManager,
)
from sk_agents.configs import TA_AUTH_STORAGE_MANAGER_CLASS, TA_AUTH_STORAGE_MANAGER_MODULE


# Clears the Singleton cache before each test.
@pytest.fixture(autouse=True)
def reset_singleton():
    # Reset Singleton before each test
    AuthStorageFactory._instances = {}
    yield
    AuthStorageFactory._instances = {}


@pytest.fixture
def mock_app_config():
    return MagicMock()


@pytest.mark.asyncio
@patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
async def test_successful_initialization_and_get_auth_storage_manager(
    mock_load_module, mock_app_config
):
    """Test successful initialization and retrieval of an authorizer."""
    mock_app_config.get.side_effect = lambda key: {
        TA_AUTH_STORAGE_MANAGER_MODULE.env_name: "dummy_module",
        TA_AUTH_STORAGE_MANAGER_CLASS.env_name: "InMemorySecureAuthStorageManager",
    }.get(key)

    dummy_module = MagicMock()
    dummy_module.InMemorySecureAuthStorageManager = InMemorySecureAuthStorageManager
    mock_load_module.return_value = dummy_module

    factory = AuthStorageFactory(mock_app_config)
    auth_storage_manager = factory.get_auth_storage_manager()  # Call the method to get the instance

    # Store some data to test retrieval
    user_id = "test_user"
    key = "test_key"
    auth_data = MagicMock()  # Mock AuthData object
    auth_storage_manager.store(user_id, key, auth_data)

    # Retrieve the stored data
    auth_storage_manager_response = auth_storage_manager.retrieve(user_id, key)
    assert isinstance(auth_storage_manager, InMemorySecureAuthStorageManager)
    assert auth_storage_manager_response == auth_data


@patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
def test_module_load_failure_raises_import_error(mock_load_module, mock_app_config):
    """Test that a module load failure raises ImportError."""
    mock_app_config.get.side_effect = lambda key: {
        TA_AUTH_STORAGE_MANAGER_MODULE.env_name: "nonexistent_module",
        TA_AUTH_STORAGE_MANAGER_CLASS.env_name: "SomeClass",
    }.get(key)

    mock_load_module.side_effect = Exception("Boom!")

    with pytest.raises(ImportError, match="Failed to load module 'nonexistent_module': Boom!"):
        AuthStorageFactory(mock_app_config)


@patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
def test_class_not_found_in_module_raises_import_error(mock_load_module, mock_app_config):
    """Test that a missing class in the module raises ImportError."""
    mock_app_config.get.side_effect = lambda key: {
        TA_AUTH_STORAGE_MANAGER_MODULE.env_name: "some_module",
        TA_AUTH_STORAGE_MANAGER_CLASS.env_name: "MissingClass",
    }.get(key)

    class DummyModule:
        def __getattr__(self, item):
            raise AttributeError(f"No attribute '{item}'")

    mock_load_module.return_value = DummyModule()

    with pytest.raises(ImportError, match="Class 'MissingClass' not found"):
        AuthStorageFactory(mock_app_config)


@patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
def test_class_not_subclass_of_request_authorizer_raises_type_error(
    mock_load_module, mock_app_config
):
    """Test that a class not subclassing AuthStorageManager raises TypeError."""

    class InvalidAuthorizer:
        pass

    mock_app_config.get.side_effect = lambda key: {
        TA_AUTH_STORAGE_MANAGER_MODULE.env_name: "some_module",
        TA_AUTH_STORAGE_MANAGER_CLASS.env_name: "InvalidAuthorizer",
    }.get(key)

    dummy_module = MagicMock()
    dummy_module.InvalidAuthorizer = InvalidAuthorizer
    mock_load_module.return_value = dummy_module

    with pytest.raises(
        TypeError, match="Class 'InvalidAuthorizer' is not a subclass of AuthStorageManager."
    ):
        AuthStorageFactory(mock_app_config)


def test_missing_module_env_variable_raises_value_error(mock_app_config):
    """Test that a missing module environment variable raises ValueError."""
    mock_app_config.get.side_effect = (
        lambda key: None if key == TA_AUTH_STORAGE_MANAGER_MODULE.env_name else "SomeClass"
    )

    with pytest.raises(
        ValueError, match="Environment variable AUTH_STORAGE_MANAGER_MODULE is not set."
    ):
        AuthStorageFactory(mock_app_config)


def test_missing_class_env_variable_raises_value_error(mock_app_config):
    """Test that a missing class environment variable raises ValueError."""
    mock_app_config.get.side_effect = (
        lambda key: "some.module" if key == TA_AUTH_STORAGE_MANAGER_MODULE.env_name else None
    )

    with pytest.raises(
        ValueError, match="Environment variable AUTH_STORAGE_MANAGER_CLASS is not set."
    ):
        AuthStorageFactory(mock_app_config)
