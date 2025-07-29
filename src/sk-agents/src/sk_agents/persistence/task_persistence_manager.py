from abc import ABC, abstractmethod

from ..tealagents.models import AgentTask


class TaskPersistenceManager(ABC):
    @abstractmethod
    async def create(task: AgentTask) -> None:
        pass

    @abstractmethod
    async def load(task_id: str) -> AgentTask | None:
        pass

    @abstractmethod
    async def update(task: AgentTask) -> None:
        pass

    @abstractmethod
    async def delete(task_id: str) -> None:
        pass

    @abstractmethod
    async def load_by_request_id(self, request_id: str) -> AgentTask | None:
        pass
