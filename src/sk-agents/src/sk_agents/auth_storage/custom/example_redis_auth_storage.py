"""
Complete Redis Authentication Storage Implementation

This example demonstrates a full-featured, production-ready Redis-based authentication storage
implementation. It serves as a complete alternative to the default in-memory storage.

To use this implementation, set the following environment variables:

TA_AUTH_STORAGE_MANAGER_MODULE=src/sk_agents/auth_storage/custom/example_redis_auth_storage.py
TA_AUTH_STORAGE_MANAGER_CLASS=RedisSecureAuthStorageManager

Required Redis configuration environment variables:
- TA_REDIS_HOST (default: localhost)
- TA_REDIS_PORT (default: 6379)
- TA_REDIS_DB (default: 0)
- TA_REDIS_TTL (default: 3600 seconds)
- TA_REDIS_PWD (optional)
- TA_REDIS_SSL (default: false)
"""

import json
import threading

import redis
from ska_utils import AppConfig

from sk_agents.auth_storage.models import AuthData
from sk_agents.auth_storage.secure_auth_storage_manager import SecureAuthStorageManager
from sk_agents.configs import (
    TA_REDIS_DB,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_PWD,
    TA_REDIS_SSL,
    TA_REDIS_TTL,
)


class RedisSecureAuthStorageManager(SecureAuthStorageManager):
    def __init__(self, app_config: AppConfig = None):
        """
        Initialize the Redis-based auth storage manager.

        Args:
            app_config: Application configuration object. If None, creates a new one.
        """
        if app_config is None:
            app_config = AppConfig()

        self.app_config = app_config
        self._lock = threading.Lock()

        # Get Redis configuration
        redis_host = self.app_config.get(TA_REDIS_HOST.env_name) or "localhost"
        redis_port = int(self.app_config.get(TA_REDIS_PORT.env_name) or 6379)
        redis_db = int(self.app_config.get(TA_REDIS_DB.env_name) or 0)
        redis_password = self.app_config.get(TA_REDIS_PWD.env_name)
        redis_ssl = self.app_config.get(TA_REDIS_SSL.env_name) == "false"
        self.ttl = int(self.app_config.get(TA_REDIS_TTL.env_name) or 3600)  # Default 1 hour

        # Initialize Redis client
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            password=redis_password,
            ssl=redis_ssl,
            decode_responses=True,  # Automatically decode responses to strings
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )

        # Test connection
        try:
            self.redis_client.ping()
        except redis.ConnectionError as e:
            raise ConnectionError(f"Failed to connect to Redis: {e}") from e

    def _get_redis_key(self, user_id: str, key: str) -> str:
        """Generate a Redis key for the given user_id and key."""
        return f"auth_storage:{user_id}:{key}"

    def _serialize_auth_data(self, data: AuthData) -> str:
        """Serialize AuthData to JSON string."""
        return data.model_dump_json()

    def _deserialize_auth_data(self, data_str: str) -> AuthData:
        """Deserialize JSON string to AuthData."""
        data_dict = json.loads(data_str)
        # Import here to avoid circular imports
        from sk_agents.auth_storage.models import AuthData

        return AuthData.model_validate(data_dict)

    def store(self, user_id: str, key: str, data: AuthData) -> None:
        """Store authorization data for a given user and key with TTL."""
        with self._lock:
            try:
                redis_key = self._get_redis_key(user_id, key)
                serialized_data = self._serialize_auth_data(data)

                # Store with TTL
                self.redis_client.setex(redis_key, self.ttl, serialized_data)

            except redis.RedisError as e:
                raise RuntimeError(f"Failed to store auth data in Redis: {e}") from e

    def retrieve(self, user_id: str, key: str) -> AuthData | None:
        """Retrieve authorization data for a given user and key."""
        with self._lock:
            try:
                redis_key = self._get_redis_key(user_id, key)
                data_str = self.redis_client.get(redis_key)

                if data_str is None:
                    return None

                return self._deserialize_auth_data(data_str)

            except redis.RedisError as e:
                raise RuntimeError(f"Failed to retrieve auth data from Redis: {e}") from e
            except (json.JSONDecodeError, ValueError) as e:
                # If we can't deserialize the data, it's corrupted, so delete it
                try:
                    redis_key = self._get_redis_key(user_id, key)
                    self.redis_client.delete(redis_key)
                except redis.RedisError:
                    pass  # Ignore deletion errors
                raise ValueError(
                    f"Corrupted auth data found for user {user_id}, key {key}: {e}"
                ) from e

    def delete(self, user_id: str, key: str) -> None:
        """Delete authorization data for a given user and key."""
        with self._lock:
            try:
                redis_key = self._get_redis_key(user_id, key)
                self.redis_client.delete(redis_key)

            except redis.RedisError as e:
                raise RuntimeError(f"Failed to delete auth data from Redis: {e}") from e

    def clear_user_data(self, user_id: str) -> int:
        """
        Clear all authorization data for a given user.

        Returns:
            Number of keys deleted.
        """
        with self._lock:
            try:
                pattern = self._get_redis_key(user_id, "*")
                keys = self.redis_client.keys(pattern)

                if not keys:
                    return 0

                return self.redis_client.delete(*keys)

            except redis.RedisError as e:
                raise RuntimeError(f"Failed to clear user data from Redis: {e}") from e

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            self.redis_client.ping()
            return True
        except redis.RedisError:
            return False
