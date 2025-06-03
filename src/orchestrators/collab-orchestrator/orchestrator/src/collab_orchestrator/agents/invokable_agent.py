from collections.abc import AsyncIterable
from typing import Any

from httpx_sse import ServerSentEvent
from pydantic import BaseModel

from collab_orchestrator.agents import AgentGateway, BaseAgent
from collab_orchestrator.co_types import InvokeResponse, PartialResponse


class InvokableAgent:
    def __init__(self, agent: BaseAgent, gateway: AgentGateway):
        self.agent = agent
        self.gateway = gateway

    async def invoke(self, agent_input: BaseModel) -> Any:
        return await self.gateway.invoke_agent(
            agent_name=self.agent.name,
            agent_version=self.agent.version,
            agent_input=agent_input,
        )

    async def invoke_sse(
        self, agent_input: BaseModel
    ) -> AsyncIterable[PartialResponse | InvokeResponse | ServerSentEvent]:
        async for content in self.gateway.invoke_agent_sse(
            agent_name=self.agent.name,
            agent_version=self.agent.version,
            agent_input=agent_input,
        ):
            yield content
