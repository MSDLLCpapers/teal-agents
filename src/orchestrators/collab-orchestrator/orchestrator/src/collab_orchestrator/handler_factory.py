from typing import List

from collab_orchestrator.agents import (
    AgentGateway,
    BaseAgentBuilder,
    BaseAgent,
    TaskAgent,
)
from collab_orchestrator.co_types import BaseConfig, KindHandler
from collab_orchestrator.planning_handler.planning_handler import PlanningHandler
from collab_orchestrator.team_handler.team_handler import TeamHandler
from ska_utils import Singleton
from ska_utils import Telemetry


class HandlerFactory(metaclass=Singleton):
    _HANDLERS = {
        "PlanningOrchestrator": PlanningHandler,
        "TeamOrchestrator": TeamHandler,
    }

    def __init__(
        self,
        t: Telemetry,
        config: BaseConfig,
        agent_gateway: AgentGateway,
        base_agent_builder: BaseAgentBuilder,
        task_agents_bases: List[BaseAgent],
        task_agents: List[TaskAgent],
    ):
        self.t = t
        self.config = config
        self.agent_gateway = agent_gateway
        self.base_agent_builder = base_agent_builder
        self.task_agents_bases = task_agents_bases
        self.task_agents = task_agents
        self._handlers = {}

    def is_valid_handler(self, handler_type: str) -> bool:
        return handler_type in self._HANDLERS

    def get_handler(self, handler_type: str) -> KindHandler:
        if handler_type not in self._HANDLERS:
            raise ValueError(f"Unknown handler type: {handler_type}")

        if handler_type not in self._handlers:
            self._handlers[handler_type] = self._HANDLERS[handler_type](
                self.t,
                self.config,
                self.agent_gateway,
                self.base_agent_builder,
                self.task_agents_bases,
                self.task_agents,
            )

        return self._handlers[handler_type]
