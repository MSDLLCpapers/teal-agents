from abc import ABC, abstractmethod

from sk_agents.tealagents.models import AgentTask


class TaskPersistenceManager(ABC):
    @abstractmethod
    async def create(self, task: AgentTask) -> None:
        pass

    @abstractmethod
    async def load(self, task_id: str) -> AgentTask | None:
        pass

    @abstractmethod
    async def update(self, task: AgentTask) -> None:
        pass

    @abstractmethod
    async def delete(self, task_id: str) -> None:
        pass

    @abstractmethod
    async def load_by_request_id(self, request_id: str) -> AgentTask | None:
        pass
