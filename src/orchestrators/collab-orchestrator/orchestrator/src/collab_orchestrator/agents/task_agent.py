from collections.abc import AsyncIterable

from httpx_sse import ServerSentEvent
from pydantic import BaseModel
from ska_utils import get_telemetry

from collab_orchestrator.agents.agent_gateway import AgentGateway
from collab_orchestrator.agents.agent_types import BaseAgent
from collab_orchestrator.agents.invokable_agent import InvokableAgent
from collab_orchestrator.co_types import (
    BaseMultiModalInput,
    ContentType,
    HistoryMultiModalMessage,
    InvokeResponse,
    MultiModalItem,
    PartialResponse,
)


class PreRequisite(BaseModel):
    goal: str
    result: str


class TaskAgent(InvokableAgent):
    def __init__(self, agent: BaseAgent, gateway: AgentGateway):
        super().__init__(agent, gateway)
        self._logger = get_telemetry().get_logger(self.__class__.__name__)

    @staticmethod
    def _pre_requisite_to_item(
        pre_requisite: PreRequisite,
    ) -> list[HistoryMultiModalMessage]:
        user_message = HistoryMultiModalMessage(
            role="user",
            items=[MultiModalItem(content_type=ContentType.TEXT, content=pre_requisite.goal)],
        )
        assistant_message = HistoryMultiModalMessage(
            role="assistant",
            items=[MultiModalItem(content_type=ContentType.TEXT, content=pre_requisite.result)],
        )
        return [user_message, assistant_message]

    @staticmethod
    def _build_chat_history(
        session_id: str, goal: str, pre_reqs: list[PreRequisite] | None = None
    ) -> BaseMultiModalInput:
        chat_history_messages: list[HistoryMultiModalMessage] = []
        for pre_req in pre_reqs:
            chat_history_messages.extend(TaskAgent._pre_requisite_to_item(pre_req))
        chat_history_messages.append(
            HistoryMultiModalMessage(
                role="user",
                items=[MultiModalItem(content_type=ContentType.TEXT, content=goal)],
            )
        )
        return BaseMultiModalInput(session_id=session_id, chat_history=chat_history_messages)

    async def perform_task_sse(
        self,
        session_id: str,
        goal: str,
        pre_requisites: list[PreRequisite] | None = None,
    ) -> AsyncIterable[PartialResponse | InvokeResponse | ServerSentEvent]:
        self._logger.debug(f"Performing task with goal: {goal}")
        chat_history = TaskAgent._build_chat_history(session_id, goal, pre_requisites)
        self._logger.debug(f"Chat history: {chat_history}")
        async for response in self.invoke_sse(chat_history):
            yield response

    async def perform_task(
        self,
        session_id: str,
        goal: str,
        pre_requisites: list[PreRequisite] | None = None,
    ) -> InvokeResponse:
        self._logger.debug(f"Performing task with goal: {goal}")
        chat_history = TaskAgent._build_chat_history(session_id, goal, pre_requisites)
        self._logger.debug(f"Chat history: {chat_history}")
        response = await self.invoke(chat_history)
        return InvokeResponse(**response)
