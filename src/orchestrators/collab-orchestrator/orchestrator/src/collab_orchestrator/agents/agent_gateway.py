from typing import Any, AsyncIterable

import aiohttp
import httpx
import websockets
from httpx_sse import aconnect_sse, ServerSentEvent
from opentelemetry.propagate import inject
from pydantic import BaseModel

from collab_orchestrator.co_types.responses import PartialResponse, InvokeResponse


class AgentGateway(BaseModel):
    host: str
    secure: bool
    agw_key: str

    def _get_endpoint_for_agent(self, agent_name: str, agent_version: str) -> str:
        protocol = "https" if self.secure else "http"
        return f"{protocol}://{self.host}/{agent_name}/{agent_version}"

    def _get_sse_endpoint_for_agent(self, agent_name: str, agent_version: str) -> str:
        protocol = "https" if self.secure else "http"
        return f"{protocol}://{self.host}/{agent_name}/{agent_version}/sse"

    def _get_ws_endpoint_for_agent(self, agent_name: str, agent_version: str) -> str:
        protocol = "wss" if self.secure else "ws"
        return f"{protocol}://{self.host}/{agent_name}/{agent_version}/stream"

    async def invoke_agent(
        self,
        session: aiohttp.ClientSession,
        agent_name: str,
        agent_version: str,
        agent_input: BaseModel,
    ) -> Any:
        payload = agent_input.model_dump_json()

        headers = {
            "taAgwKey": self.agw_key,
            "Content-Type": "application/json",
        }
        inject(headers)
        async with session.post(
            self._get_endpoint_for_agent(agent_name, agent_version),
            data=payload,
            headers=headers,
        ) as response:
            response.raise_for_status()
            return await response.json()

    async def invoke_agent_sse(
        self, agent_name: str, agent_version: str, agent_input: BaseModel
    ) -> AsyncIterable[PartialResponse | InvokeResponse | ServerSentEvent]:
        json_input = agent_input.model_dump(mode="json")
        headers = {
            "taAgwKey": self.agw_key,
        }
        endpoint = self._get_sse_endpoint_for_agent(agent_name, agent_version)
        async with httpx.AsyncClient(timeout=30.0) as client:
            async with aconnect_sse(
                client,
                "POST",
                endpoint,
                json=json_input,
                headers=headers,
            ) as event_source:
                async for sse in event_source.aiter_sse():
                    match sse.event:
                        case "partial-response":
                            yield PartialResponse.model_validate_json(sse.data)
                        case "final-response":
                            yield InvokeResponse.model_validate_json(sse.data)
                        case _:
                            yield sse

    async def invoke_agent_stream(
        self, agent_name: str, agent_version: str, agent_input: BaseModel
    ) -> AsyncIterable[str]:
        payload = agent_input.model_dump_json()

        headers = {
            "taAgwKey": self.agw_key,
        }
        inject(headers)
        async with websockets.connect(
            self._get_ws_endpoint_for_agent(agent_name, agent_version),
            additional_headers=headers,
        ) as ws:
            await ws.send(payload)
            async for message in ws:
                yield message
