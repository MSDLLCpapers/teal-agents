import logging
from enum import Enum

from pydantic import BaseModel

from collab_orchestrator.agents import BaseAgent, InvokableAgent
from collab_orchestrator.co_types import (
    BaseMultiModalInput,
    HistoryMultiModalMessage,
)

logger = logging.getLogger(__name__)

class TeamBaseAgent(BaseModel):
    name: str
    description: str


class ConversationMessage(BaseModel):
    task_id: str
    agent_name: str
    instructions: str
    result: str


class ManagerInput(BaseModel):
    chat_history: list[HistoryMultiModalMessage] | None = None
    overall_goal: str
    agent_list: list[TeamBaseAgent]
    conversation: list[ConversationMessage] | None = None


class Action(Enum):
    PROVIDE_RESULT = "provide_result"
    ABORT = "abort"
    ASSIGN_NEW_TASK = "assign_new_task"


class ResultOutput(BaseModel):
    result_task_id: str
    result: str


class AbortOutput(BaseModel):
    abort_reason: str


class AssignTaskOutput(BaseModel):
    task_id: str
    agent_name: str
    instructions: str


class ManagerOutput(BaseModel):
    session_id: str | None = None
    source: str | None = None
    request_id: str | None = None

    next_action: Action
    action_detail: ResultOutput | AbortOutput | AssignTaskOutput


class ManagerAgent(InvokableAgent):
    async def determine_next_action(
        self,
        chat_history: BaseMultiModalInput,
        overall_goal: str,
        task_agents: list[BaseAgent],
        conversation: list[ConversationMessage],
    ) -> ManagerOutput:
        team_task_agents = [
            TeamBaseAgent(name=f"{agent.name}:{agent.version}", description=agent.description)
            for agent in task_agents
        ]
        request = ManagerInput(
            chat_history=chat_history.chat_history,
            overall_goal=overall_goal,
            agent_list=team_task_agents,
            conversation=conversation,
        )
        logger.info("Begin building response ")
        response = await self.invoke(request)
        return ManagerOutput(**response["output_pydantic"])
