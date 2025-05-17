from typing import Any, AsyncIterable

import aiohttp
from httpx_sse import ServerSentEvent
from pydantic import BaseModel

from collab_orchestrator.agents import BaseAgent, AgentGateway
from collab_orchestrator.co_types.responses import PartialResponse, InvokeResponse


class InvokableAgent:
    def __init__(self, agent: BaseAgent, gateway: AgentGateway):
        self.agent = agent
        self.gateway = gateway

    async def invoke(
        self, session: aiohttp.ClientSession, agent_input: BaseModel
    ) -> Any:
        return await self.gateway.invoke_agent(
            session=session,
            agent_name=self.agent.name,
            agent_version=self.agent.version,
            agent_input=agent_input,
        )

    async def invoke_stream(self, agent_input: BaseModel) -> AsyncIterable[str]:
        async for content in self.gateway.invoke_agent_stream(
            agent_name=self.agent.name,
            agent_version=self.agent.version,
            agent_input=agent_input,
        ):
            yield content

    async def invoke_sse(
        self, agent_input: BaseModel
    ) -> AsyncIterable[PartialResponse | InvokeResponse | ServerSentEvent]:
        async for content in self.gateway.invoke_agent_sse(
            agent_name=self.agent.name,
            agent_version=self.agent.version,
            agent_input=agent_input,
        ):
            yield content
