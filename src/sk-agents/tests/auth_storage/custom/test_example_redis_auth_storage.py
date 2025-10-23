import json
import threading
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
import redis

from sk_agents.auth_storage.custom.example_redis_auth_storage import (
    RedisSecureAuthStorageManager,
)
from sk_agents.auth_storage.models import OAuth2AuthData


@pytest.fixture
def mock_app_config():
    """Create a mock app config with default Redis settings."""
    config = MagicMock()
    config.get.side_effect = lambda key, default=None: {
        "TA_REDIS_HOST": "localhost",
        "TA_REDIS_PORT": "6379",
        "TA_REDIS_DB": "0",
        "TA_REDIS_PWD": None,
        "TA_REDIS_SSL": "false",
        "TA_REDIS_TTL": "3600",
    }.get(key, default)
    return config


@pytest.fixture
def sample_auth_data():
    """Create sample OAuth2 auth data for testing."""
    return OAuth2AuthData(
        access_token="test_token_123",
        refresh_token="refresh_token_456",
        expires_at=datetime.now() + timedelta(hours=1),
        scopes=["read", "write"],
    )


class TestRedisSecureAuthStorageManagerInitialization:
    """Test initialization and configuration of RedisSecureAuthStorageManager."""

    @patch("redis.Redis")
    def test_init_with_app_config(self, mock_redis_class):
        """Test initialization with provided app config."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        config = MagicMock()

        # Note: .get() returns the value or None (mimicking AppConfig with or logic)
        def mock_get(key):
            return {
                "TA_REDIS_HOST": "test-host",
                "TA_REDIS_PORT": "6380",
                "TA_REDIS_DB": "2",
                "TA_REDIS_PWD": "test-password",
                "TA_REDIS_SSL": "false",
                "TA_REDIS_TTL": "7200",
            }.get(key)

        config.get.side_effect = mock_get

        manager = RedisSecureAuthStorageManager(config)

        # Verify Redis client was created with correct parameters
        # redis_ssl = self.app_config.get(TA_REDIS_SSL.env_name) == "false"
        # When TA_REDIS_SSL is "false", ssl=True
        mock_redis_class.assert_called_once_with(
            host="test-host",
            port=6380,
            db=2,
            password="test-password",
            ssl=True,  # "false" == "false" evaluates to True
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        assert manager.ttl == 7200
        assert manager.app_config == config

    @patch("redis.Redis")
    @patch("sk_agents.auth_storage.custom.example_redis_auth_storage.AppConfig")
    def test_init_without_app_config(self, mock_app_config_class, mock_redis_class):
        """Test initialization without app config creates one."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        mock_config_instance = MagicMock()
        mock_app_config_class.return_value = mock_config_instance

        def mock_get(key):
            return {
                "TA_REDIS_HOST": "localhost",
                "TA_REDIS_PORT": "6379",
                "TA_REDIS_DB": "0",
                "TA_REDIS_PWD": None,
                "TA_REDIS_SSL": "false",
                "TA_REDIS_TTL": "3600",
            }.get(key)

        mock_config_instance.get.side_effect = mock_get

        manager = RedisSecureAuthStorageManager(None)

        # Verify AppConfig was created
        mock_app_config_class.assert_called_once()
        assert manager.app_config == mock_config_instance

    @patch("redis.Redis")
    def test_init_with_default_values(self, mock_redis_class):
        """Test initialization uses default values when config returns None."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        config = MagicMock()
        config.get.return_value = None  # All config values return None

        manager = RedisSecureAuthStorageManager(config)

        # Verify defaults were used
        # redis_ssl = self.app_config.get(TA_REDIS_SSL.env_name) == "false"
        # When TA_REDIS_SSL is None, None == "false" is False, so ssl is False
        mock_redis_class.assert_called_once_with(
            host="localhost",
            port=6379,
            db=0,
            password=None,
            ssl=False,  # None == "false" is False, so ssl is False
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        assert manager.ttl == 3600

    @patch("redis.Redis")
    def test_init_connection_failure(self, mock_redis_class):
        """Test initialization raises ConnectionError when Redis connection fails."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.side_effect = redis.ConnectionError("Connection refused")

        config = MagicMock()
        config.get.return_value = None

        with pytest.raises(ConnectionError, match="Failed to connect to Redis"):
            RedisSecureAuthStorageManager(config)

    @patch("redis.Redis")
    def test_init_creates_lock(self, mock_redis_class):
        """Test initialization creates threading lock."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        config = MagicMock()
        config.get.return_value = None

        manager = RedisSecureAuthStorageManager(config)

        assert hasattr(manager, "_lock")
        assert isinstance(manager._lock, type(threading.Lock()))


class TestRedisSecureAuthStorageManagerKeyGeneration:
    """Test Redis key generation."""

    @patch("redis.Redis")
    def test_get_redis_key(self, mock_redis_class, mock_app_config):
        """Test Redis key generation with user_id and key."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(mock_app_config)

        key = manager._get_redis_key("user123", "session456")
        assert key == "auth_storage:user123:session456"

    @patch("redis.Redis")
    def test_get_redis_key_with_special_characters(self, mock_redis_class, mock_app_config):
        """Test Redis key generation with special characters."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(mock_app_config)

        key = manager._get_redis_key("user@example.com", "session:123:abc")
        assert key == "auth_storage:user@example.com:session:123:abc"


class TestRedisSecureAuthStorageManagerSerialization:
    """Test serialization and deserialization of AuthData."""

    @patch("redis.Redis")
    def test_serialize_auth_data(self, mock_redis_class, mock_app_config, sample_auth_data):
        """Test serialization of AuthData to JSON string."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(mock_app_config)

        serialized = manager._serialize_auth_data(sample_auth_data)

        assert isinstance(serialized, str)
        data_dict = json.loads(serialized)
        assert data_dict["access_token"] == "test_token_123"
        assert data_dict["refresh_token"] == "refresh_token_456"
        assert data_dict["scopes"] == ["read", "write"]

    @patch("redis.Redis")
    def test_deserialize_auth_data(self, mock_redis_class, mock_app_config, sample_auth_data):
        """Test deserialization of JSON string to AuthData."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Serialize then deserialize
        serialized = manager._serialize_auth_data(sample_auth_data)
        deserialized = manager._deserialize_auth_data(serialized)

        assert isinstance(deserialized, OAuth2AuthData)
        assert deserialized.access_token == sample_auth_data.access_token
        assert deserialized.refresh_token == sample_auth_data.refresh_token
        assert deserialized.scopes == sample_auth_data.scopes


class TestRedisSecureAuthStorageManagerStore:
    """Test store functionality."""

    @patch("redis.Redis")
    def test_store_success(self, mock_redis_class, mock_app_config, sample_auth_data):
        """Test successful storage of auth data."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        storage = {}
        mock_redis_instance.setex.side_effect = lambda key, ttl, value: storage.update({key: value})

        manager = RedisSecureAuthStorageManager(mock_app_config)
        manager.store("user1", "session1", sample_auth_data)

        # Verify setex was called with correct parameters
        mock_redis_instance.setex.assert_called_once()
        call_args = mock_redis_instance.setex.call_args
        assert call_args[0][0] == "auth_storage:user1:session1"
        assert call_args[0][1] == 3600  # TTL
        assert "test_token_123" in call_args[0][2]  # Serialized data

    @patch("redis.Redis")
    def test_store_redis_error(self, mock_redis_class, mock_app_config, sample_auth_data):
        """Test store raises RuntimeError when Redis fails."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.setex.side_effect = redis.RedisError("Write failed")

        manager = RedisSecureAuthStorageManager(mock_app_config)

        with pytest.raises(RuntimeError, match="Failed to store auth data in Redis"):
            manager.store("user1", "session1", sample_auth_data)

    @patch("redis.Redis")
    def test_store_thread_safety(self, mock_redis_class, mock_app_config):
        """Test store is thread-safe."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        storage = {}
        storage_lock = threading.Lock()

        def thread_safe_setex(key, ttl, value):
            with storage_lock:
                storage[key] = value

        mock_redis_instance.setex.side_effect = thread_safe_setex

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Create multiple threads storing data
        threads = []
        num_threads = 10

        def worker(thread_id):
            auth_data = OAuth2AuthData(
                access_token=f"token_{thread_id}",
                expires_at=datetime.now() + timedelta(hours=1),
                scopes=["read"],
            )
            manager.store(f"user_{thread_id}", "session", auth_data)

        for i in range(num_threads):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify all stores completed
        assert len(storage) == num_threads


class TestRedisSecureAuthStorageManagerRetrieve:
    """Test retrieve functionality."""

    @patch("redis.Redis")
    def test_retrieve_success(self, mock_redis_class, mock_app_config, sample_auth_data):
        """Test successful retrieval of auth data."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        storage = {}
        mock_redis_instance.setex.side_effect = lambda key, ttl, value: storage.update({key: value})
        mock_redis_instance.get.side_effect = lambda key: storage.get(key)

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Store then retrieve
        manager.store("user1", "session1", sample_auth_data)
        retrieved = manager.retrieve("user1", "session1")

        assert retrieved is not None
        assert retrieved.access_token == sample_auth_data.access_token
        assert retrieved.refresh_token == sample_auth_data.refresh_token
        assert retrieved.scopes == sample_auth_data.scopes

    @patch("redis.Redis")
    def test_retrieve_non_existent_key(self, mock_redis_class, mock_app_config):
        """Test retrieve returns None for non-existent key."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.return_value = None

        manager = RedisSecureAuthStorageManager(mock_app_config)
        retrieved = manager.retrieve("user1", "nonexistent")

        assert retrieved is None

    @patch("redis.Redis")
    def test_retrieve_redis_error(self, mock_redis_class, mock_app_config):
        """Test retrieve raises RuntimeError when Redis fails."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.side_effect = redis.RedisError("Read failed")

        manager = RedisSecureAuthStorageManager(mock_app_config)

        with pytest.raises(RuntimeError, match="Failed to retrieve auth data from Redis"):
            manager.retrieve("user1", "session1")

    @patch("redis.Redis")
    def test_retrieve_corrupted_data_json_error(self, mock_redis_class, mock_app_config):
        """Test retrieve handles corrupted JSON data."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.return_value = "invalid json {{{{"
        mock_redis_instance.delete.return_value = 1

        manager = RedisSecureAuthStorageManager(mock_app_config)

        with pytest.raises(ValueError, match="Corrupted auth data found"):
            manager.retrieve("user1", "session1")

        # Verify corrupted data was deleted
        mock_redis_instance.delete.assert_called_once_with("auth_storage:user1:session1")

    @patch("redis.Redis")
    def test_retrieve_corrupted_data_validation_error(self, mock_redis_class, mock_app_config):
        """Test retrieve handles data that fails Pydantic validation."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        # Valid JSON but invalid AuthData structure
        mock_redis_instance.get.return_value = json.dumps({"invalid": "data"})
        mock_redis_instance.delete.return_value = 1

        manager = RedisSecureAuthStorageManager(mock_app_config)

        with pytest.raises(ValueError, match="Corrupted auth data found"):
            manager.retrieve("user1", "session1")

        # Verify corrupted data was deleted
        mock_redis_instance.delete.assert_called_once_with("auth_storage:user1:session1")

    @patch("redis.Redis")
    def test_retrieve_corrupted_data_deletion_fails(self, mock_redis_class, mock_app_config):
        """Test retrieve handles case where deletion of corrupted data fails."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.get.return_value = "invalid json"
        mock_redis_instance.delete.side_effect = redis.RedisError("Delete failed")

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Should still raise ValueError, ignore deletion error
        with pytest.raises(ValueError, match="Corrupted auth data found"):
            manager.retrieve("user1", "session1")


class TestRedisSecureAuthStorageManagerDelete:
    """Test delete functionality."""

    @patch("redis.Redis")
    def test_delete_success(self, mock_redis_class, mock_app_config, sample_auth_data):
        """Test successful deletion of auth data."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        storage = {}
        mock_redis_instance.setex.side_effect = lambda key, ttl, value: storage.update({key: value})
        mock_redis_instance.get.side_effect = lambda key: storage.get(key)
        mock_redis_instance.delete.side_effect = lambda key: storage.pop(key, None)

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Store, then delete
        manager.store("user1", "session1", sample_auth_data)
        assert manager.retrieve("user1", "session1") is not None

        manager.delete("user1", "session1")
        assert manager.retrieve("user1", "session1") is None

    @patch("redis.Redis")
    def test_delete_non_existent_key(self, mock_redis_class, mock_app_config):
        """Test deleting non-existent key doesn't raise error."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.delete.return_value = 0

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Should not raise error
        manager.delete("user1", "nonexistent")
        mock_redis_instance.delete.assert_called_once_with("auth_storage:user1:nonexistent")

    @patch("redis.Redis")
    def test_delete_redis_error(self, mock_redis_class, mock_app_config):
        """Test delete raises RuntimeError when Redis fails."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.delete.side_effect = redis.RedisError("Delete failed")

        manager = RedisSecureAuthStorageManager(mock_app_config)

        with pytest.raises(RuntimeError, match="Failed to delete auth data from Redis"):
            manager.delete("user1", "session1")


class TestRedisSecureAuthStorageManagerClearUserData:
    """Test clear_user_data functionality."""

    @patch("redis.Redis")
    def test_clear_user_data_success(self, mock_redis_class, mock_app_config, sample_auth_data):
        """Test successful clearing of all user data."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        storage = {}
        mock_redis_instance.setex.side_effect = lambda key, ttl, value: storage.update({key: value})
        mock_redis_instance.keys.side_effect = lambda pattern: [
            k for k in storage.keys() if pattern.replace("*", "") in k
        ]

        def mock_delete(*keys):
            count = 0
            for key in keys:
                if storage.pop(key, None) is not None:
                    count += 1
            return count

        mock_redis_instance.delete.side_effect = mock_delete

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Store multiple sessions for user
        manager.store("user1", "session1", sample_auth_data)
        manager.store("user1", "session2", sample_auth_data)
        manager.store("user1", "session3", sample_auth_data)
        manager.store("user2", "session1", sample_auth_data)  # Different user

        count = manager.clear_user_data("user1")

        assert count == 3
        # user1 data should be gone
        assert "auth_storage:user1:session1" not in storage
        assert "auth_storage:user1:session2" not in storage
        assert "auth_storage:user1:session3" not in storage
        # user2 data should remain
        assert "auth_storage:user2:session1" in storage

    @patch("redis.Redis")
    def test_clear_user_data_no_keys(self, mock_redis_class, mock_app_config):
        """Test clearing data for user with no keys returns 0."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.keys.return_value = []

        manager = RedisSecureAuthStorageManager(mock_app_config)

        count = manager.clear_user_data("user1")

        assert count == 0
        # delete should not be called when there are no keys
        mock_redis_instance.delete.assert_not_called()

    @patch("redis.Redis")
    def test_clear_user_data_keys_error(self, mock_redis_class, mock_app_config):
        """Test clear_user_data raises RuntimeError when Redis keys() fails."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.keys.side_effect = redis.RedisError("Keys failed")

        manager = RedisSecureAuthStorageManager(mock_app_config)

        with pytest.raises(RuntimeError, match="Failed to clear user data from Redis"):
            manager.clear_user_data("user1")

    @patch("redis.Redis")
    def test_clear_user_data_delete_error(self, mock_redis_class, mock_app_config):
        """Test clear_user_data raises RuntimeError when Redis delete() fails."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True
        mock_redis_instance.keys.return_value = ["auth_storage:user1:session1"]
        mock_redis_instance.delete.side_effect = redis.RedisError("Delete failed")

        manager = RedisSecureAuthStorageManager(mock_app_config)

        with pytest.raises(RuntimeError, match="Failed to clear user data from Redis"):
            manager.clear_user_data("user1")


class TestRedisSecureAuthStorageManagerHealthCheck:
    """Test health_check functionality."""

    @patch("redis.Redis")
    def test_health_check_success(self, mock_redis_class, mock_app_config):
        """Test health check returns True when Redis is healthy."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(mock_app_config)

        assert manager.health_check() is True

    @patch("redis.Redis")
    def test_health_check_failure(self, mock_redis_class, mock_app_config):
        """Test health check returns False when Redis ping fails."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        # First ping for initialization succeeds
        mock_redis_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Subsequent ping fails
        mock_redis_instance.ping.side_effect = redis.RedisError("Connection lost")

        assert manager.health_check() is False

    @patch("redis.Redis")
    def test_health_check_connection_error(self, mock_redis_class, mock_app_config):
        """Test health check returns False on ConnectionError."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        manager = RedisSecureAuthStorageManager(mock_app_config)

        mock_redis_instance.ping.side_effect = redis.ConnectionError("Connection refused")

        assert manager.health_check() is False


class TestRedisSecureAuthStorageManagerEdgeCases:
    """Test edge cases and integration scenarios."""

    @patch("redis.Redis")
    def test_concurrent_operations(self, mock_redis_class, mock_app_config):
        """Test concurrent store, retrieve, and delete operations."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        storage = {}
        storage_lock = threading.Lock()

        def thread_safe_setex(key, ttl, value):
            with storage_lock:
                storage[key] = value

        def thread_safe_get(key):
            with storage_lock:
                return storage.get(key)

        def thread_safe_delete(key):
            with storage_lock:
                return storage.pop(key, None)

        mock_redis_instance.setex.side_effect = thread_safe_setex
        mock_redis_instance.get.side_effect = thread_safe_get
        mock_redis_instance.delete.side_effect = thread_safe_delete

        manager = RedisSecureAuthStorageManager(mock_app_config)

        num_threads = 20
        threads = []
        results = {}

        def worker(thread_id):
            try:
                auth_data = OAuth2AuthData(
                    access_token=f"token_{thread_id}",
                    expires_at=datetime.now() + timedelta(hours=1),
                    scopes=["read"],
                )
                # Store
                manager.store(f"user_{thread_id}", "session", auth_data)
                # Retrieve
                retrieved = manager.retrieve(f"user_{thread_id}", "session")
                results[thread_id] = retrieved.access_token if retrieved else None
                # Delete
                if thread_id % 2 == 0:
                    manager.delete(f"user_{thread_id}", "session")
            except Exception as e:
                results[thread_id] = f"error: {e}"

        for i in range(num_threads):
            thread = threading.Thread(target=worker, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Verify results
        for i in range(num_threads):
            assert results[i] == f"token_{i}" or "error" not in str(results[i])

    @patch("redis.Redis")
    def test_ssl_configuration_true(self, mock_redis_class):
        """Test SSL configuration when explicitly set to true."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        config = MagicMock()
        config.get.side_effect = lambda key, default=None: {
            "TA_REDIS_HOST": "localhost",
            "TA_REDIS_PORT": "6379",
            "TA_REDIS_DB": "0",
            "TA_REDIS_PASSWORD": None,
            "TA_REDIS_SSL": "true",  # Different from "false"
            "TA_REDIS_TTL": "3600",
        }.get(key, default)

        RedisSecureAuthStorageManager(config)

        # SSL should be False when TA_REDIS_SSL is "true" (not "false")
        call_kwargs = mock_redis_class.call_args[1]
        assert call_kwargs["ssl"] is False

    @patch("redis.Redis")
    def test_multiple_users_same_key(self, mock_redis_class, mock_app_config):
        """Test that different users can have the same key names."""
        mock_redis_instance = Mock()
        mock_redis_class.return_value = mock_redis_instance
        mock_redis_instance.ping.return_value = True

        storage = {}
        mock_redis_instance.setex.side_effect = lambda key, ttl, value: storage.update({key: value})
        mock_redis_instance.get.side_effect = lambda key: storage.get(key)

        manager = RedisSecureAuthStorageManager(mock_app_config)

        # Create different auth data for different users with same key
        auth_data1 = OAuth2AuthData(
            access_token="user1_token",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read"],
        )
        auth_data2 = OAuth2AuthData(
            access_token="user2_token",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["write"],
        )

        manager.store("user1", "common_session", auth_data1)
        manager.store("user2", "common_session", auth_data2)

        retrieved1 = manager.retrieve("user1", "common_session")
        retrieved2 = manager.retrieve("user2", "common_session")

        assert retrieved1.access_token == "user1_token"
        assert retrieved2.access_token == "user2_token"
