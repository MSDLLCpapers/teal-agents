import asyncio
from collections.abc import AsyncIterable
from typing import Any, cast

import httpx
from httpx_sse import ServerSentEvent, aconnect_sse
from opentelemetry.propagate import inject
from pydantic import BaseModel
from ska_utils import KeepaliveMessage, get_telemetry

from collab_orchestrator.co_types import (
    InvokeResponse,
    PartialResponse,
)

_TIMEOUT = 600.0


class AgentGateway(BaseModel):
    host: str
    secure: bool
    agw_key: str

    def __init__(self, host: str, secure: bool, agw_key: str):
        super().__init__(host=host, secure=secure, agw_key=agw_key)
        self._logger = get_telemetry().get_logger(self.__class__.__name__)

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
        agent_name: str,
        agent_version: str,
        agent_input: BaseModel,
    ) -> Any:
        self._logger.info("Begin processing invoke agent")
        payload = agent_input.model_dump_json()

        headers = {
            "taAgwKey": self.agw_key,
            "Content-Type": "application/json",
        }
        inject(headers)

        max_retries = 3
        attempt = 0
        last_exception = None
        while attempt < max_retries:
            try:
                # Create a new client for each attempt to avoid connection reuse issues
                async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                    self._logger.info(
                        f"Invoking agent {agent_name}:{agent_version} ({attempt + 1}/{max_retries})"
                    )
                    self._logger.info("Beginning response processing")
                    response = await client.post(
                        self._get_endpoint_for_agent(agent_name, agent_version),
                        content=payload,
                        headers=headers,
                    )
                    response.raise_for_status()
                    return response.json()
            except httpx.TimeoutException as e:
                last_exception = e
                self._logger.warning(
                    f"Timeout invoking agent {agent_name} ({attempt + 1}/{max_retries}): {e}"
                )
                # Add a small delay before retry to allow resources to clear
                await asyncio.sleep(1)
                attempt += 1
            except Exception as e:
                last_exception = e
                self._logger.warning(
                    f"Error invoking agent {agent_name} ({attempt + 1}/{max_retries}): {e}"
                )
                attempt += 1
        # More specific error message with the actual exception
        self._logger.error(
            f"All {max_retries} attempts failed for agent {agent_name}: {last_exception}"
        )
        raise last_exception or TimeoutError("Max retries exceeded")

    async def _process_sse_event(
        self, sse: Any
    ) -> PartialResponse | InvokeResponse | ServerSentEvent | None:
        """Process an SSE event and return the appropriate response or None if no response."""
        if sse is None:
            return None

        sse_event = cast(ServerSentEvent, sse)
        if sse_event.event == "partial-response":
            return PartialResponse.model_validate_json(sse_event.data)
        elif sse_event.event == "final-response":
            self._logger.debug("Sent final response")
            return InvokeResponse.model_validate_json(sse_event.data)
        else:
            return sse_event

    async def invoke_agent_sse(
        self, agent_name: str, agent_version: str, agent_input: BaseModel
    ) -> AsyncIterable[PartialResponse | InvokeResponse | KeepaliveMessage | ServerSentEvent]:
        self._logger.info("Begin processing invoke agent sse")
        json_input = agent_input.model_dump(mode="json")
        headers = {
            "taAgwKey": self.agw_key,
        }
        inject(headers)
        endpoint = self._get_sse_endpoint_for_agent(agent_name, agent_version)

        # Create the keepalive task
        keepalive_task = asyncio.create_task(asyncio.sleep(30))
        first_event_received = False

        self._logger.debug(f"Invoking agent {agent_name}:{agent_version} SSE endpoint")
        self._logger.info("Beginning response processing")
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with aconnect_sse(
                client,
                "POST",
                endpoint,
                json=json_input,
                headers=headers,
            ) as event_source:
                # Set up the stream iterator
                sse_iter = event_source.aiter_sse()

                while True:
                    # Either wait for the next SSE event or for the keepalive timer
                    if not first_event_received:
                        done, pending = await asyncio.wait(
                            [asyncio.create_task(anext(sse_iter)), keepalive_task],
                            return_when=asyncio.FIRST_COMPLETED,
                        )

                        # Check if the keepalive timer completed
                        if keepalive_task in done:
                            # Send a keepalive and create a new timer
                            self._logger.debug("Sending keepalive response")
                            yield KeepaliveMessage()
                            keepalive_task = asyncio.create_task(asyncio.sleep(30))
                            continue

                        # We got an SSE event
                        for task in done:
                            if task != keepalive_task:
                                try:
                                    sse = await task
                                    if sse is None:
                                        continue
                                    first_event_received = True
                                    # Cancel the keepalive task, we don't need it anymore
                                    keepalive_task.cancel()

                                    # Process the event
                                    response = await self._process_sse_event(sse)
                                    if response is not None:
                                        yield response
                                        if isinstance(response, InvokeResponse):
                                            return
                                except Exception as e:
                                    self._logger.error(f"Error processing SSE event: {e}")
                                    raise e
                    else:
                        # After first event, just process the stream normally
                        try:
                            sse = await anext(sse_iter)
                            if sse is not None:
                                response = await self._process_sse_event(sse)
                                if response is not None:
                                    yield response
                                    if isinstance(response, InvokeResponse):
                                        return  # Exit when we get the final response
                        except StopAsyncIteration:
                            break  # Exit when the stream is done
