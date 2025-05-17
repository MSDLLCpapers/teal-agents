from typing import List, AsyncIterable

from httpx_sse import ServerSentEvent
from pydantic import BaseModel

from collab_orchestrator.agents.invokable_agent import InvokableAgent
from collab_orchestrator.co_types.requests import (
    HistoryMultiModalMessage,
    MultiModalItem,
    ContentType,
    BaseMultiModalInput,
)
from collab_orchestrator.co_types.responses import PartialResponse, InvokeResponse


class PreRequisite(BaseModel):
    goal: str
    result: str


class TaskAgent(InvokableAgent):
    @staticmethod
    def _pre_requisite_to_item(
        pre_requisite: PreRequisite,
    ) -> List[HistoryMultiModalMessage]:
        user_message = HistoryMultiModalMessage(
            role="user",
            items=[
                MultiModalItem(
                    content_type=ContentType.TEXT, content=pre_requisite.goal
                )
            ],
        )
        assistant_message = HistoryMultiModalMessage(
            role="assistant",
            items=[
                MultiModalItem(
                    content_type=ContentType.TEXT, content=pre_requisite.result
                )
            ],
        )
        return [user_message, assistant_message]

    @staticmethod
    def _build_chat_history(
        session_id: str, goal: str, pre_reqs: List[PreRequisite] | None = None
    ) -> BaseMultiModalInput:
        chat_history_messages: List[HistoryMultiModalMessage] = []
        for pre_req in pre_reqs:
            chat_history_messages.extend(TaskAgent._pre_requisite_to_item(pre_req))
        chat_history_messages.append(
            HistoryMultiModalMessage(
                role="user",
                items=[MultiModalItem(content_type=ContentType.TEXT, content=goal)],
            )
        )
        return BaseMultiModalInput(
            session_id=session_id, chat_history=chat_history_messages
        )

    async def perform_task_sse(
        self,
        session_id: str,
        goal: str,
        pre_requisites: List[PreRequisite] | None = None,
    ) -> AsyncIterable[PartialResponse | InvokeResponse | ServerSentEvent]:
        chat_history = TaskAgent._build_chat_history(session_id, goal, pre_requisites)
        async for response in self.invoke_sse(chat_history):
            yield response
