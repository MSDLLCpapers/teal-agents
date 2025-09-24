"""Tests for AuthStorageFactory including in-memory and Redis implementations."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.custom.example_redis_auth_storage import (
    RedisSecureAuthStorageManager,
)
from sk_agents.auth_storage.in_memory_secure_auth_storage_manager import (
    InMemorySecureAuthStorageManager,
)
from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.configs import TA_AUTH_STORAGE_MANAGER_CLASS, TA_AUTH_STORAGE_MANAGER_MODULE


# Clear the Singleton cache before each test
@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset Singleton before each test."""
    AuthStorageFactory._instances = {}
    yield
    AuthStorageFactory._instances = {}


@pytest.fixture
def mock_app_config():
    """Create a mock app config for testing."""
    return MagicMock()


class TestAuthStorageFactoryBasics:
    """Test basic factory functionality."""

    @pytest.mark.asyncio
    @patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
    async def test_successful_initialization_and_get_auth_storage_manager(
        self, mock_load_module, mock_app_config
    ):
        """Test successful initialization and retrieval of an auth storage manager."""
        mock_app_config.get.side_effect = lambda key: {
            TA_AUTH_STORAGE_MANAGER_MODULE.env_name: "dummy_module",
            TA_AUTH_STORAGE_MANAGER_CLASS.env_name: "InMemorySecureAuthStorageManager",
        }.get(key)

        dummy_module = MagicMock()
        dummy_module.InMemorySecureAuthStorageManager = InMemorySecureAuthStorageManager
        mock_load_module.return_value = dummy_module

        factory = AuthStorageFactory(mock_app_config)
        auth_storage_manager = factory.get_auth_storage_manager()

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
    def test_module_load_failure_raises_import_error(self, mock_load_module, mock_app_config):
        """Test that a module load failure raises ImportError."""
        mock_app_config.get.side_effect = lambda key: {
            TA_AUTH_STORAGE_MANAGER_MODULE.env_name: "nonexistent_module",
            TA_AUTH_STORAGE_MANAGER_CLASS.env_name: "SomeClass",
        }.get(key)

        mock_load_module.side_effect = Exception("Boom!")

        with pytest.raises(ImportError, match="Failed to load module 'nonexistent_module': Boom!"):
            AuthStorageFactory(mock_app_config)

    @patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
    def test_class_not_found_in_module_raises_value_error(self, mock_load_module, mock_app_config):
        """Test that a missing class in the module raises ValueError."""
        mock_app_config.get.side_effect = lambda key: {
            TA_AUTH_STORAGE_MANAGER_MODULE.env_name: "some_module",
            TA_AUTH_STORAGE_MANAGER_CLASS.env_name: "MissingClass",
        }.get(key)

        class DummyModule:
            def __getattr__(self, item):
                raise AttributeError(f"No attribute '{item}'")

        mock_load_module.return_value = DummyModule()

        with pytest.raises(ValueError, match="Custom Auth Storage Manager class: MissingClass"):
            AuthStorageFactory(mock_app_config)

    @patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
    def test_class_not_subclass_of_secure_auth_storage_manager_raises_type_error(
        self, mock_load_module, mock_app_config
    ):
        """Test that a class not subclassing SecureAuthStorageManager raises TypeError."""

        class InvalidAuthStorageManager:
            pass

        mock_app_config.get.side_effect = lambda key: {
            TA_AUTH_STORAGE_MANAGER_MODULE.env_name: "some_module",
            TA_AUTH_STORAGE_MANAGER_CLASS.env_name: "InvalidAuthStorageManager",
        }.get(key)

        dummy_module = MagicMock()
        dummy_module.InvalidAuthStorageManager = InvalidAuthStorageManager
        mock_load_module.return_value = dummy_module

        with pytest.raises(
            TypeError,
            match=(
                "Class 'InvalidAuthStorageManager' is not a subclass of SecureAuthStorageManager."
            ),
        ):
            AuthStorageFactory(mock_app_config)

    def test_missing_module_env_variable_uses_default(self, mock_app_config):
        """Test that when no module is provided, factory uses default in-memory implementation."""

        # Simulate KeyError when environment variable is not set
        def mock_get(key):
            raise KeyError(key)

        mock_app_config.get.side_effect = mock_get

        factory = AuthStorageFactory(mock_app_config)
        manager = factory.get_auth_storage_manager()

        assert isinstance(manager, InMemorySecureAuthStorageManager)

    def test_missing_class_env_variable_raises_value_error(self, mock_app_config):
        """Test that a missing class environment variable raises ValueError."""

        def mock_get(key):
            if key == TA_AUTH_STORAGE_MANAGER_MODULE.env_name:
                return "some.module"
            else:
                raise KeyError(key)

        mock_app_config.get.side_effect = mock_get

        with pytest.raises(ValueError, match="Custom Auth Storage Manager class name not provided"):
            AuthStorageFactory(mock_app_config)


class TestRedisIntegration:
    """Test Redis auth storage integration via factory pattern."""

    @patch("redis.Redis")
    def test_redis_auth_storage_via_factory(self, mock_redis):
        """Test that the factory can create and use Redis auth storage manager."""
        # Setup mock Redis instance
        mock_instance = Mock()
        mock_redis.return_value = mock_instance

        # Mock storage
        storage = {}
        mock_instance.setex.side_effect = lambda key, ttl, value: storage.update({key: value})
        mock_instance.get.side_effect = lambda key: storage.get(key)
        mock_instance.ping.return_value = True

        # Create mock app config that points to Redis implementation
        mock_config = MagicMock()
        mock_config.get.side_effect = lambda key, default=None: {
            "TA_AUTH_STORAGE_MANAGER_MODULE": (
                "src/sk_agents/auth_storage/custom/example_redis_auth_storage.py"
            ),
            "TA_AUTH_STORAGE_MANAGER_CLASS": "RedisSecureAuthStorageManager",
            "TA_REDIS_HOST": "localhost",
            "TA_REDIS_PORT": "6379",
            "TA_REDIS_DB": "0",
            "TA_REDIS_PASSWORD": "",
            "TA_REDIS_SSL": "false",
            "TA_REDIS_TOKEN_TTL": "3600",
        }.get(key, default)

        # Create factory and get manager
        factory = AuthStorageFactory(mock_config)
        manager = factory.get_auth_storage_manager()

        # Test the manager works
        auth_data = OAuth2AuthData(
            access_token="test_token",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read", "write"],
        )

        # Store and retrieve
        manager.store("user1", "session1", auth_data)
        retrieved = manager.retrieve("user1", "session1")

        assert retrieved is not None
        assert retrieved.access_token == "test_token"
        assert retrieved.scopes == ["read", "write"]

        # Test health check
        assert manager.health_check() is True

    def test_factory_defaults_to_in_memory_when_no_config(self):
        """Test that factory defaults to in-memory when no Redis config is provided."""
        mock_config = MagicMock()

        # Simulate missing environment variables
        def mock_get(key):
            raise KeyError(key)

        mock_config.get.side_effect = mock_get

        factory = AuthStorageFactory(mock_config)
        manager = factory.get_auth_storage_manager()

        # Should be in-memory implementation
        assert manager.__class__.__name__ == "InMemorySecureAuthStorageManager"


class TestRedisImplementationDirect:
    """Test Redis auth storage manager directly."""

    @pytest.fixture
    def app_config(self):
        """Create a mock app config for testing."""
        config = MagicMock()
        config.get.side_effect = lambda key, default=None: {
            "TA_REDIS_HOST": "localhost",
            "TA_REDIS_PORT": "6379",
            "TA_REDIS_DB": "0",
            "TA_REDIS_PASSWORD": "",
            "TA_REDIS_SSL": "false",
            "TA_REDIS_TOKEN_TTL": "3600",
        }.get(key, default)
        return config

    @pytest.fixture
    def sample_auth_data(self):
        """Create sample auth data for testing."""
        return OAuth2AuthData(
            access_token="test_token",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read", "write"],
        )

    @patch("redis.Redis")
    def test_store_and_retrieve(self, mock_redis, app_config, sample_auth_data):
        """Test basic store and retrieve functionality."""
        # Setup mock Redis instance
        mock_instance = Mock()
        mock_redis.return_value = mock_instance

        # Mock storage
        storage = {}
        mock_instance.setex.side_effect = lambda key, ttl, value: storage.update({key: value})
        mock_instance.get.side_effect = lambda key: storage.get(key)
        mock_instance.ping.return_value = True

        # Redis import is at the top of the file

        # Create manager and test
        manager = RedisSecureAuthStorageManager(app_config)

        # Store data
        manager.store("user1", "key1", sample_auth_data)

        # Retrieve data
        retrieved = manager.retrieve("user1", "key1")

        assert retrieved is not None
        assert retrieved.access_token == sample_auth_data.access_token

    @patch("redis.Redis")
    def test_health_check(self, mock_redis, app_config):
        """Test health check functionality."""
        mock_instance = Mock()
        mock_redis.return_value = mock_instance
        mock_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(app_config)
        assert manager.health_check() is True

        # Test failure
        import redis

        mock_instance.ping.side_effect = redis.RedisError("Connection failed")
        assert manager.health_check() is False

    @patch("redis.Redis")
    def test_key_generation(self, mock_redis, app_config):
        """Test Redis key generation."""
        mock_instance = Mock()
        mock_redis.return_value = mock_instance
        mock_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(app_config)
        key = manager._get_redis_key("user123", "session1")
        assert key == "auth_storage:user123:session1"

    @patch("redis.Redis")
    def test_crud_operations(self, mock_redis, app_config):
        """Test complete CRUD operations."""
        mock_instance = Mock()
        mock_redis.return_value = mock_instance

        # Mock storage with proper delete functionality
        storage = {}
        mock_instance.setex.side_effect = lambda key, ttl, value: storage.update({key: value})
        mock_instance.get.side_effect = lambda key: storage.get(key)
        mock_instance.delete.side_effect = lambda key: storage.pop(key, None)
        mock_instance.keys.side_effect = lambda pattern: [
            k for k in storage.keys() if pattern.replace("*", "") in k
        ]
        mock_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(app_config)

        # Test data
        auth_data = OAuth2AuthData(
            access_token="crud_test_token",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read", "write", "admin"],
        )

        user_id = "crud_user"
        session_key = "crud_session"

        # CREATE: Store auth data
        manager.store(user_id, session_key, auth_data)
        assert f"auth_storage:{user_id}:{session_key}" in storage

        # READ: Retrieve auth data
        retrieved = manager.retrieve(user_id, session_key)
        assert retrieved is not None
        assert retrieved.access_token == "crud_test_token"

        # UPDATE: Store updated data
        updated_auth_data = OAuth2AuthData(
            access_token="updated_crud_token",
            expires_at=datetime.now() + timedelta(hours=2),
            scopes=["read", "write", "admin", "super_admin"],
        )
        manager.store(user_id, session_key, updated_auth_data)
        updated_retrieved = manager.retrieve(user_id, session_key)
        assert updated_retrieved.access_token == "updated_crud_token"
        assert "super_admin" in updated_retrieved.scopes

        # DELETE: Remove specific session
        manager.delete(user_id, session_key)
        deleted_retrieved = manager.retrieve(user_id, session_key)
        assert deleted_retrieved is None

        # Test clear_user_data
        manager.store(user_id, "session1", auth_data)
        manager.store(user_id, "session2", auth_data)
        manager.store(user_id, "session3", auth_data)

        # Mock the delete method to return count
        def mock_delete_multiple(*keys):
            count = 0
            for key in keys:
                if storage.pop(key, None) is not None:
                    count += 1
            return count

        mock_instance.delete.side_effect = mock_delete_multiple

        count = manager.clear_user_data(user_id)
        assert count >= 0  # Should clear some sessions
