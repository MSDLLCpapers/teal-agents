"""
DEPRECATION NOTICE: A2A (Agent-to-Agent) functionality is being deprecated
as part of the framework migration evaluation. This module is maintained for
backward compatibility only. New development should avoid using A2A functionality.

Redis implementation of the TaskStore interface.
This implementation uses Redis as the persistent store for Task objects.
"""

import json

from a2a.server.tasks.task_store import TaskStore
from a2a.types import Task
from redis.asyncio import Redis


class RedisTaskStore(TaskStore):
    """Redis implementation of the TaskStore interface.

    This class provides Redis-based persistence for Task objects.
    """

    def __init__(self, redis_client: Redis, ttl: int | None = None, key_prefix: str = "task:"):
        """Initialize the RedisTaskStore with a Redis client.

        Args:
            redis_client: An instance of Redis client
            key_prefix: Prefix used for Redis keys (default: "task:")
        """
        self._redis = redis_client
        self._ttl = ttl
        self._key_prefix = key_prefix

    def _get_key(self, task_id: str) -> str:
        """Generate a Redis key for a given task ID.

        Args:
            task_id: The ID of the task

        Returns:
            A Redis key string
        """
        return f"{self._key_prefix}{task_id}"

    async def save(self, task: Task):
        """Saves or updates a task in the Redis store.

        Args:
            task: The Task object to save
        """
        # Convert the Task object to a serializable dictionary
        task_dict = task.model_dump(mode="json")

        # Serialize the task dictionary to JSON
        task_json = json.dumps(task_dict)

        # Store the serialized task in Redis using the task ID as the key
        await self._redis.set(self._get_key(task.id), task_json, ex=self._ttl)

    async def get(self, task_id: str) -> Task | None:
        """Retrieves a task from the Redis store by ID.

        Args:
            task_id: The ID of the task to retrieve

        Returns:
            The Task object if found, None otherwise
        """
        # Get the serialized task from Redis
        task_json = await self._redis.get(self._get_key(task_id))

        if task_json is None:
            return None

        # Deserialize the JSON string to a dictionary
        task_dict = json.loads(task_json)

        # Create and return a Task object from the dictionary
        return Task.model_validate(task_dict)

    async def delete(self, task_id: str):
        """Deletes a task from the Redis store by ID.

        Args:
            task_id: The ID of the task to delete
        """
        # Delete the task from Redis
        await self._redis.delete(self._get_key(task_id))
