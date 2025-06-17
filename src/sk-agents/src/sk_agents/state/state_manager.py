from abc import ABC, abstractmethod

from sk_agents.ska_types import HistoryMultiModalMessage


class StateManager(ABC):
    @abstractmethod
    async def update_task_messages(
        self, task_id: str, new_message: HistoryMultiModalMessage
    ) -> list[HistoryMultiModalMessage]:
        pass

    @abstractmethod
    async def set_canceled(self, task_id: str) -> None:
        pass

    @abstractmethod
    async def is_canceled(self, task_id) -> bool:
        pass


