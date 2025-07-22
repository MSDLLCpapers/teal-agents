# In-memory implementation
import asyncio
import logging
import threading

from src.sk_agents.exceptions import (
    PersistenceCreateError,
    PersistenceDeleteError,
    PersistenceLoadError,
    PersistenceUpdateError,
)
from src.sk_agents.persistence.task_persistence_manager import TaskPersistenceManager
from src.sk_agents.tealagents.models import AgentTask

logger = logging.getLogger(__name__)


class InMemoryPersistenceManager(TaskPersistenceManager):
    def __init__(self):
        self.in_memory: dict[str, AgentTask] = {}
        logger.info("InMemoryPersistenceManager initialized.")

        self._lock = threading.Lock()

    async def create(self, task: AgentTask) -> None:
        async with self._lock:
            try:
                if task.task_id in self.in_memory:
                    raise PersistenceCreateError(
                        message=f"Task with ID '{task.task_id}' already exists."
                    )
                self.in_memory[task.task_id] = task
                logger.info(f"Task '{task.task_id}' created successfully.")
            except Exception as e:
                raise PersistenceCreateError(
                    message=f"Unexpected error creating task '{task.task_id}': {e}"
                ) from e

    async def load(self, task_id: str) -> AgentTask | None:
        async with self._lock:
            try:
                task = self.in_memory[task_id]
                logger.info(f"Task '{task_id}' loaded successfully.")
                return task
            except KeyError:
                raise PersistenceLoadError(
                    message=f"Task '{task_id}' provided not found in memory"
                ) from None
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
                self.in_memory[task.task_id] = task
                logger.info(f"Task '{task.task_id}' updated successfully.")

            except Exception as e:
                raise PersistenceUpdateError(
                    message=f"Unexpected error updating task '{task.task_id}': {e}"
                ) from e

    async def delete(self, task_id: str) -> None:
        with self._lock:
            try:
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
