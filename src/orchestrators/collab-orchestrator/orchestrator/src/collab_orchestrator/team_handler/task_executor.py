from contextlib import nullcontext
from typing import List, AsyncIterable

from httpx_sse import ServerSentEvent
from ska_utils import get_telemetry

from collab_orchestrator.agents import TaskAgent
from collab_orchestrator.co_types import (
    new_event_response,
    EventType,
    AgentRequestEvent,
)
from collab_orchestrator.co_types.responses import (
    PartialResponse,
    InvokeResponse,
    ErrorResponse,
)
from collab_orchestrator.team_handler.conversation import Conversation


class TaskExecutor:
    def __init__(self, agents: List[TaskAgent]):
        self.agents = {}
        for agent in agents:
            self.agents[f"{agent.agent.name}:{agent.agent.version}"] = agent
        self.t = get_telemetry()

    async def execute_task_sse(
        self,
        task_id: str,
        instructions: str,
        agent_name: str,
        conversation: Conversation,
        session_id: str | None = None,
        source: str | None = None,
        request_id: str | None = None,
    ) -> AsyncIterable[str]:
        with (
            self.t.tracer.start_as_current_span(
                name="execute-task",
                attributes={"instructions": instructions, "agent_name": agent_name},
            )
            if self.t.telemetry_enabled()
            else nullcontext()
        ):
            task_agent = self.agents[agent_name]
            if not task_agent:
                raise ValueError(f"Task agent {agent_name} not found.")

            yield new_event_response(
                EventType.AGENT_REQUEST,
                AgentRequestEvent(
                    session_id=session_id,
                    source=source,
                    request_id=request_id,
                    task_id=task_id,
                    agent_name=agent_name,
                    task_goal=instructions,
                ),
            )

            task_result = ""
            pre_reqs = conversation.to_pre_requisites()
            async for content in task_agent.perform_task_sse(
                session_id, instructions, pre_reqs
            ):
                if isinstance(content, PartialResponse):
                    yield new_event_response(EventType.PARTIAL_RESPONSE, content)
                elif isinstance(content, InvokeResponse):
                    task_result = content.output_raw
                    yield new_event_response(EventType.FINAL_RESPONSE, content)
                elif isinstance(content, ServerSentEvent):
                    yield f"event: {content.event}\ndata: {content.data}\n\n"
                else:
                    yield new_event_response(
                        EventType.ERROR,
                        ErrorResponse(
                            session_id=session_id,
                            source=source,
                            request_id=request_id,
                            status_code=500,
                            detail=f"Unknown response type - {str(content)}",
                        ),
                    )
            conversation.add_item(task_id, agent_name, instructions, task_result)
