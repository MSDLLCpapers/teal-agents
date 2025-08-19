# In-memory implementation
import asyncio
import logging

from sk_agents.exceptions import (
    PersistenceCreateError,
    PersistenceDeleteError,
    PersistenceLoadError,
    PersistenceUpdateError,
)
from sk_agents.persistence.task_persistence_manager import TaskPersistenceManager
from sk_agents.tealagents.models import AgentTask

logger = logging.getLogger(__name__)


class InMemoryPersistenceManager(TaskPersistenceManager):
    def __init__(self):
        self.in_memory: dict[str, AgentTask] = {}
        self.item_request_id_index: dict[
            str, set[str]
        ] = {}  # Maps request_id to set of task_ids that contain it
        logger.info("InMemoryPersistenceManager initialized.")
        self._lock = asyncio.Lock()

    async def create(self, task: AgentTask) -> None:
        async with self._lock:
            try:
                if task.task_id in self.in_memory:
                    raise PersistenceCreateError(
                        message=f"Task with ID '{task.task_id}' already exists."
                    )
                self.in_memory[task.task_id] = task

                # Update the item_request_id_index
                for item in task.items:
                    if item.request_id not in self.item_request_id_index:
                        self.item_request_id_index[item.request_id] = set()
                    self.item_request_id_index[item.request_id].add(task.task_id)

                logger.info(f"Task '{task.task_id}' created successfully.")

            except Exception as e:
                raise PersistenceCreateError(
                    message=f"Unexpected error creating task '{task.task_id}': {e}"
                ) from e

    async def load(self, task_id: str) -> AgentTask | None:
        async with self._lock:
            try:
                task = self.in_memory.get(task_id)
                if task is None:
                    logger.info(f"Task '{task_id}' not found in memory.")
                    return None
                logger.info(f"Task '{task_id}' loaded successfully.")
                return task
            except Exception as e:
                raise PersistenceLoadError(
                    message=f"Unexpected error loading task {task_id} with error message: {e}"
                ) from e

    async def update(self, task: AgentTask) -> None:
        async with self._lock:
            try:
                if task.task_id not in self.in_memory:
                    raise PersistenceUpdateError(
                        f"Task with ID '{task.task_id}' does not exist for update."
                    )

                old_task = self.in_memory[task.task_id]

                # Remove old request_id associations
                for item in old_task.items:
                    if item.request_id in self.item_request_id_index:
                        self.item_request_id_index[item.request_id].discard(task.task_id)
                        if not self.item_request_id_index[item.request_id]:
                            del self.item_request_id_index[item.request_id]

                # Update the main storage
                self.in_memory[task.task_id] = task

                # Add new request_id associations
                for item in task.items:
                    if item.request_id not in self.item_request_id_index:
                        self.item_request_id_index[item.request_id] = set()
                    self.item_request_id_index[item.request_id].add(task.task_id)

                logger.info(f"Task '{task.task_id}' updated successfully.")

            except Exception as e:
                raise PersistenceUpdateError(
                    message=f"Unexpected error updating task '{task.task_id}': {e}"
                ) from e

    async def delete(self, task_id: str) -> None:
        async with self._lock:
            try:
                task = self.in_memory[task_id]

                # Remove from request_id index
                for item in task.items:
                    if item.request_id in self.item_request_id_index:
                        self.item_request_id_index[item.request_id].discard(task_id)
                        if not self.item_request_id_index[item.request_id]:
                            del self.item_request_id_index[item.request_id]

                # Remove from main storage
                del self.in_memory[task_id]

                logger.info(f"Task '{task_id}' deleted successfully.")
            except KeyError:
                raise PersistenceDeleteError(
                    message=f"Task with ID '{task_id}' does not exist for deletion."
                ) from None
            except Exception as e:
                raise PersistenceDeleteError(
                    message=f"Unexpected error deleting task '{task_id}': {e}"
                ) from e

    async def load_by_request_id(self, request_id: str) -> AgentTask | None:
        async with self._lock:
            try:
                task_ids = self.item_request_id_index.get(request_id, set())
                if not task_ids:
                    logger.info(f"No tasks found for request_id '{request_id}'.")
                    return None

                # If multiple tasks have the same request_id, return the first one
                task_id = next(iter(task_ids))
                task = self.in_memory[task_id]
                logger.info(f"Found task '{task_id}' for request_id '{request_id}'.")
                return task
            except Exception as e:
                raise PersistenceLoadError(
                    message=f"Unexpected error loading tasks by request_id '{request_id}': {e}"
                ) from e
