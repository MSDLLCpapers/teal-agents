import asyncio
from contextlib import nullcontext
from typing import AsyncIterable, List, Dict

from httpx_sse import ServerSentEvent
from ska_utils import get_telemetry

from collab_orchestrator.agents import TaskAgent
from collab_orchestrator.agents.task_agent import PreRequisite
from collab_orchestrator.co_types import (
    new_event_response,
    EventType,
    AgentRequestEvent,
    ErrorResponse,
)
from collab_orchestrator.co_types.responses import PartialResponse, InvokeResponse
from collab_orchestrator.planning_handler.plan import ExecutableTask, TaskStatus, Step


class StepExecutor:
    def __init__(self, task_agents: List[TaskAgent]):
        self.task_agents: Dict[str, TaskAgent] = {}
        for task_agent in task_agents:
            self.task_agents[f"{task_agent.agent.name}:{task_agent.agent.version}"] = (
                task_agent
            )
        self.task_accumulator: Dict[str, ExecutableTask] = {}
        self.t = get_telemetry()

    @staticmethod
    def _task_to_pre_requisite(task: ExecutableTask) -> PreRequisite:
        return PreRequisite(goal=task.task_goal, result=task.result)

    async def _execute_task_sse(
        self, session_id: str, source: str, request_id: str, task: ExecutableTask
    ) -> AsyncIterable[str]:
        with (
            self.t.tracer.start_as_current_span(
                name="execute-task",
                attributes={"task": task.task_id, "goal": task.task_goal},
            )
            if self.t.telemetry_enabled()
            else nullcontext()
        ):
            task_agent = self.task_agents[task.task_agent]
            if not task_agent:
                raise ValueError(f"Task agent {task.task_agent} not found.")
            pre_requisites: List[PreRequisite] = [
                StepExecutor._task_to_pre_requisite(
                    self.task_accumulator[pre_requisite]
                )
                for pre_requisite in task.prerequisite_tasks
            ]
            async for content in task_agent.perform_task_sse(
                session_id, task.task_goal, pre_requisites
            ):
                if isinstance(content, PartialResponse):
                    yield new_event_response(EventType.PARTIAL_RESPONSE, content)
                elif isinstance(content, InvokeResponse):
                    task.result = content.output_raw
                    task.status = TaskStatus.DONE
                    self.task_accumulator[task.task_id] = task
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

    async def execute_step_sse(
        self, session_id: str, source: str, request_id: str, step: Step
    ) -> AsyncIterable[str]:
        with (
            self.t.tracer.start_as_current_span(
                name="execute-step", attributes={"step": str(step.step_number)}
            )
            if self.t.telemetry_enabled()
            else nullcontext()
        ):

            async def process_task(task) -> AsyncIterable[str]:
                yield new_event_response(
                    EventType.AGENT_REQUEST,
                    AgentRequestEvent(
                        session_id=session_id,
                        source=source,
                        request_id=request_id,
                        task_id=task.task_id,
                        agent_name=task.task_agent,
                        task_goal=task.task_goal,
                    ),
                )
                async for result in self._execute_task_sse(
                    session_id, source, request_id, task
                ):
                    yield result

            streams = [process_task(task) for task in step.step_tasks]
            async for result in self._merge_async_iterables(streams):
                yield result

    async def _merge_async_iterables(
        self, async_iterables: List[AsyncIterable[str]]
    ) -> AsyncIterable[str]:
        async def consume(iterable, queue):
            async for item in iterable:
                await queue.put(item)
            await queue.put(None)  # Signal the end of the iterable

        queue = asyncio.Queue()
        consumers = [
            asyncio.create_task(consume(iterable, queue))
            for iterable in async_iterables
        ]
        num_finished = 0
        while num_finished < len(async_iterables):
            result = await queue.get()
            if result is None:
                num_finished += 1
            else:
                yield result
        await asyncio.gather(*consumers)
