from enum import Enum
from typing import List

import aiohttp
from collab_orchestrator.agents import BaseAgent
from collab_orchestrator.agents.invokable_agent import InvokableAgent
from pydantic import BaseModel


class TeamBaseAgent(BaseModel):
    name: str
    description: str


class ConversationMessage(BaseModel):
    task_id: str
    agent_name: str
    instructions: str
    result: str


class ManagerInput(BaseModel):
    overall_goal: str
    agent_list: List[TeamBaseAgent]
    conversation: List[ConversationMessage] | None = None


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
    next_action: Action
    action_detail: ResultOutput | AbortOutput | AssignTaskOutput


class ManagerAgent(InvokableAgent):
    async def determine_next_action(
        self,
        overall_goal: str,
        task_agents: List[BaseAgent],
        conversation: List[ConversationMessage],
    ) -> ManagerOutput:
        team_task_agents = [
            TeamBaseAgent(
                name=f"{agent.name}:{agent.version}", description=agent.description
            )
            for agent in task_agents
        ]
        request = ManagerInput(
            overall_goal=overall_goal,
            agent_list=team_task_agents,
            conversation=conversation,
        )
        async with aiohttp.ClientSession() as session:
            response = await self.invoke(session, request)
        return ManagerOutput(**response["output_pydantic"])
