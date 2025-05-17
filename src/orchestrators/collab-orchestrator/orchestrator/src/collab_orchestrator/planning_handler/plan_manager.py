from typing import List

from collab_orchestrator.agents import BaseAgent
from collab_orchestrator.co_types.requests import BaseMultiModalInput
from collab_orchestrator.planning_handler.plan import Plan
from collab_orchestrator.planning_handler.planning_agent import PlanningAgent


class PlanningFailedException(Exception):
    pass


class PlanManager:
    def __init__(self, planning_agent: PlanningAgent):
        self.planning_agent = planning_agent

    async def generate_plan(
        self,
        chat_history: BaseMultiModalInput,
        overall_goal: str,
        task_agents: List[BaseAgent],
    ) -> Plan:
        gen_plan_response = await self.planning_agent.generate_plan(
            chat_history, overall_goal, task_agents
        )
        if not gen_plan_response.can_succeed:
            raise PlanningFailedException(
                f"Planning failed: {gen_plan_response.reasoning}"
            )
        return Plan.new_from_response(gen_plan_response)
