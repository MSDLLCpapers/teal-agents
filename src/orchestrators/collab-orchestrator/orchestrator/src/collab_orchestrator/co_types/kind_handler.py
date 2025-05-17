from abc import ABC, abstractmethod
from typing import List, AsyncIterable, TYPE_CHECKING

if TYPE_CHECKING:
    from ska_utils import Telemetry

    from collab_orchestrator.agents import (
        AgentGateway,
        BaseAgentBuilder,
        BaseAgent,
        TaskAgent,
    )
    from collab_orchestrator.co_types.config import BaseConfig
    from collab_orchestrator.co_types.requests import BaseMultiModalInput


class KindHandler(ABC):
    def __init__(
        self,
        t: "Telemetry",
        config: "BaseConfig",
        agent_gateway: "AgentGateway",
        base_agent_builder: "BaseAgentBuilder",
        task_agents_bases: List["BaseAgent"],
        task_agents: List["TaskAgent"],
    ):
        self.t = t
        self.config = config
        self.agent_gateway = agent_gateway
        self.base_agent_builder = base_agent_builder
        self.task_agents_bases = task_agents_bases
        self.task_agents = task_agents

    @abstractmethod
    async def initialize(self):
        pass

    @abstractmethod
    async def invoke(
        self, chat_history: "BaseMultiModalInput", request: str
    ) -> AsyncIterable:
        pass
