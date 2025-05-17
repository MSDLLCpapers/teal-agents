from typing import List

from pydantic import BaseModel

from collab_orchestrator.agents import PreRequisite
from collab_orchestrator.team_handler.manager_agent import ConversationMessage


class Conversation(BaseModel):
    messages: List[ConversationMessage]

    def to_pre_requisites(self) -> List[PreRequisite]:
        pre_requisites: List[PreRequisite] = []
        for message in self.messages:
            pre_requisites.append(
                PreRequisite(goal=message.instructions, result=message.result)
            )
        return pre_requisites

    def add_item(self, task_id: str, agent_name: str, instructions: str, result: str):
        self.messages.append(
            ConversationMessage(
                task_id=task_id,
                agent_name=agent_name,
                instructions=instructions,
                result=result,
            )
        )

    def get_message_by_task_id(self, task_id: str) -> ConversationMessage | None:
        for message in self.messages:
            if message.task_id == task_id:
                return message
        return None
