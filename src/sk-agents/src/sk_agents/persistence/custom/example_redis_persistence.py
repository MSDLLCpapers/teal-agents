"""
Complete Redis Task Persistence Implementation

This example demonstrates a full-featured, production-ready Redis-based task persistence
implementation. It serves as a complete alternative to the default in-memory storage.

To use this implementation, set the following environment variables:

TA_PERSISTENCE_MODULE=src/sk_agents/persistence/custom/example_redis_persistence.py
TA_PERSISTENCE_CLASS=RedisTaskPersistenceManager

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

from sk_agents.configs import (
    TA_REDIS_DB,
    TA_REDIS_HOST,
    TA_REDIS_PORT,
    TA_REDIS_PWD,
    TA_REDIS_SSL,
    TA_REDIS_TTL,
)
from sk_agents.exceptions import (
    PersistenceCreateError,
    PersistenceDeleteError,
    PersistenceLoadError,
    PersistenceUpdateError,
)
from sk_agents.persistence.task_persistence_manager import TaskPersistenceManager
from sk_agents.tealagents.models import AgentTask


class RedisTaskPersistenceManager(TaskPersistenceManager):
    def __init__(self, app_config: AppConfig = None):
        """
        Initialize the Redis-based task persistence manager.

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

    def _get_task_key(self, task_id: str) -> str:
        """Generate a Redis key for the given task_id."""
        return f"task_persistence:task:{task_id}"

    def _get_request_index_key(self, request_id: str) -> str:
        """Generate a Redis key for request_id index."""
        return f"task_persistence:request_index:{request_id}"

    def _serialize_task(self, task: AgentTask) -> str:
        """Serialize AgentTask to JSON string."""
        return task.model_dump_json()

    def _deserialize_task(self, task_str: str) -> AgentTask:
        """Deserialize JSON string to AgentTask."""
        task_dict = json.loads(task_str)
        return AgentTask.model_validate(task_dict)

    async def create(self, task: AgentTask) -> None:
        """Create a new task in Redis."""
        with self._lock:
            try:
                task_key = self._get_task_key(task.task_id)

                # Check if task already exists
                if self.redis_client.exists(task_key):
                    raise PersistenceCreateError(
                        message=f"Task with ID '{task.task_id}' already exists."
                    )

                # Serialize and store the task
                serialized_task = self._serialize_task(task)
                self.redis_client.setex(task_key, self.ttl, serialized_task)

                # Update request_id indexes
                for item in task.items:
                    request_index_key = self._get_request_index_key(item.request_id)
                    self.redis_client.sadd(request_index_key, task.task_id)
                    self.redis_client.expire(request_index_key, self.ttl)

            except redis.RedisError as e:
                raise PersistenceCreateError(
                    message=f"Failed to create task '{task.task_id}' in Redis: {e}"
                ) from e
            except Exception as e:
                raise PersistenceCreateError(
                    message=f"Unexpected error creating task '{task.task_id}': {e}"
                ) from e

    async def load(self, task_id: str) -> AgentTask | None:
        """Load a task from Redis by task_id."""
        with self._lock:
            try:
                task_key = self._get_task_key(task_id)
                task_str = self.redis_client.get(task_key)

                if task_str is None:
                    return None

                return self._deserialize_task(task_str)

            except redis.RedisError as e:
                raise PersistenceLoadError(
                    message=f"Failed to load task '{task_id}' from Redis: {e}"
                ) from e
            except (json.JSONDecodeError, ValueError) as e:
                # If we can't deserialize the task, it's corrupted, so delete it
                try:
                    task_key = self._get_task_key(task_id)
                    self.redis_client.delete(task_key)
                except redis.RedisError:
                    pass  # Ignore deletion errors
                raise PersistenceLoadError(
                    message=f"Corrupted task data found for task_id {task_id}: {e}"
                ) from e

    async def update(self, task: AgentTask) -> None:
        """Update an existing task in Redis."""
        with self._lock:
            try:
                task_key = self._get_task_key(task.task_id)

                # Check if task exists
                old_task_str = self.redis_client.get(task_key)
                if old_task_str is None:
                    raise PersistenceUpdateError(
                        f"Task with ID '{task.task_id}' does not exist for update."
                    )

                # Deserialize old task to clean up old request_id indexes
                old_task = self._deserialize_task(old_task_str)

                # Remove old request_id associations
                for item in old_task.items:
                    request_index_key = self._get_request_index_key(item.request_id)
                    self.redis_client.srem(request_index_key, task.task_id)

                # Update the task
                serialized_task = self._serialize_task(task)
                self.redis_client.setex(task_key, self.ttl, serialized_task)

                # Add new request_id associations
                for item in task.items:
                    request_index_key = self._get_request_index_key(item.request_id)
                    self.redis_client.sadd(request_index_key, task.task_id)
                    self.redis_client.expire(request_index_key, self.ttl)

            except redis.RedisError as e:
                raise PersistenceUpdateError(
                    message=f"Failed to update task '{task.task_id}' in Redis: {e}"
                ) from e
            except Exception as e:
                raise PersistenceUpdateError(
                    message=f"Unexpected error updating task '{task.task_id}': {e}"
                ) from e

    async def delete(self, task_id: str) -> None:
        """Delete a task from Redis."""
        with self._lock:
            try:
                task_key = self._get_task_key(task_id)

                # Get the task first to clean up request_id indexes
                task_str = self.redis_client.get(task_key)
                if task_str is None:
                    raise PersistenceDeleteError(
                        message=f"Task with ID '{task_id}' does not exist for deletion."
                    )

                task = self._deserialize_task(task_str)

                # Remove from request_id indexes
                for item in task.items:
                    request_index_key = self._get_request_index_key(item.request_id)
                    self.redis_client.srem(request_index_key, task_id)

                # Delete the task
                self.redis_client.delete(task_key)

            except redis.RedisError as e:
                raise PersistenceDeleteError(
                    message=f"Failed to delete task '{task_id}' from Redis: {e}"
                ) from e
            except Exception as e:
                raise PersistenceDeleteError(
                    message=f"Unexpected error deleting task '{task_id}': {e}"
                ) from e

    async def load_by_request_id(self, request_id: str) -> AgentTask | None:
        """Load a task by request_id."""
        with self._lock:
            try:
                request_index_key = self._get_request_index_key(request_id)
                task_ids = self.redis_client.smembers(request_index_key)

                if not task_ids:
                    return None

                # If multiple tasks have the same request_id, return the first one
                task_id = next(iter(task_ids))
                return await self.load(task_id)

            except redis.RedisError as e:
                raise PersistenceLoadError(
                    message=f"Failed to load task by request_id '{request_id}' from Redis: {e}"
                ) from e
            except Exception as e:
                raise PersistenceLoadError(
                    message=f"Unexpected error loading task by request_id '{request_id}': {e}"
                ) from e

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            self.redis_client.ping()
            return True
        except redis.RedisError:
            return False

    def clear_all_tasks(self) -> int:
        """
        Clear all task data (useful for testing).

        Returns:
            Number of keys deleted.
        """
        with self._lock:
            try:
                # Get all task keys
                task_keys = self.redis_client.keys("task_persistence:task:*")
                request_index_keys = self.redis_client.keys("task_persistence:request_index:*")

                all_keys = task_keys + request_index_keys

                if not all_keys:
                    return 0

                return self.redis_client.delete(*all_keys)

            except redis.RedisError as e:
                raise RuntimeError(f"Failed to clear all tasks from Redis: {e}") from e
