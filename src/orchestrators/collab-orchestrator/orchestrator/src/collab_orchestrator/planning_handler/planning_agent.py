import logging

from pydantic import BaseModel

from collab_orchestrator.agents import BaseAgent, InvokableAgent
from collab_orchestrator.co_types import (
    BaseMultiModalInput,
    HistoryMultiModalMessage,
    InvokeResponse,
)

logger = logging.getLogger(__name__)

class PlanningBaseAgent(BaseModel):
    name: str
    description: str


class GeneratePlanRequest(BaseModel):
    chat_history: list[HistoryMultiModalMessage] | None = None
    overall_goal: str
    agent_list: list[PlanningBaseAgent]


class Task(BaseModel):
    task_id: str
    prerequisite_tasks: list[str]
    task_goal: str
    task_agent: str


class Step(BaseModel):
    step_number: int
    step_tasks: list[Task]


class GeneratePlanResponse(BaseModel):
    can_succeed: bool
    reasoning: str | None = None
    steps: list[Step] | None


class PlanningAgent(InvokableAgent):
    async def generate_plan(
        self,
        chat_history: BaseMultiModalInput,
        overall_goal: str,
        task_agents: list[BaseAgent],
    ) -> GeneratePlanResponse:
        planning_task_agents = [
            PlanningBaseAgent(name=f"{agent.name}:{agent.version}", description=agent.description)
            for agent in task_agents
        ]
        request = GeneratePlanRequest(
            chat_history=chat_history.chat_history,
            overall_goal=overall_goal,
            agent_list=planning_task_agents,
        )
        logger.info("Building response")
        response: InvokeResponse = await self.invoke(request)
        return GeneratePlanResponse(**response["output_pydantic"])
