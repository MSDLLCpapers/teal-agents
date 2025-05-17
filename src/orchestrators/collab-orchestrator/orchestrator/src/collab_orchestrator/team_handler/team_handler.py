import uuid
from contextlib import nullcontext
from typing import List, AsyncIterable

from ska_utils import Telemetry

from collab_orchestrator.agents import (
    AgentGateway,
    BaseAgentBuilder,
    BaseAgent,
    TaskAgent,
)
from collab_orchestrator.co_types import (
    BaseConfig,
    new_event_response,
    EventType,
    ErrorResponse,
    AbortResult,
)
from collab_orchestrator.co_types import KindHandler
from collab_orchestrator.co_types.requests import BaseMultiModalInput
from collab_orchestrator.co_types.responses import InvokeResponse, TokenUsage
from collab_orchestrator.team_handler.conversation import Conversation
from collab_orchestrator.team_handler.manager_agent import (
    ManagerAgent,
    Action,
)
from collab_orchestrator.team_handler.task_executor import TaskExecutor
from collab_orchestrator.team_handler.types import TeamSpec


class TeamHandler(KindHandler):
    def __init__(
        self,
        t: Telemetry,
        config: BaseConfig,
        agent_gateway: AgentGateway,
        base_agent_builder: BaseAgentBuilder,
        task_agents_bases: List[BaseAgent],
        task_agents: List[TaskAgent],
    ):
        super().__init__(
            t, config, agent_gateway, base_agent_builder, task_agents_bases, task_agents
        )
        self.manager_agent: ManagerAgent | None = None
        self.max_rounds = 0
        self.task_executor: TaskExecutor | None = None

    async def _execute_task(
        self,
        task_id: str,
        instructions: str,
        agent_name: str,
        conversation: Conversation,
        session_id: str | None = None,
        source: str | None = None,
        request_id: str | None = None,
    ) -> AsyncIterable[str]:
        async for result in self.task_executor.execute_task_sse(
            task_id=task_id,
            instructions=instructions,
            agent_name=agent_name,
            conversation=conversation,
            session_id=session_id,
            source=source,
            request_id=request_id,
        ):
            yield result

    async def initialize(self):
        spec = TeamSpec.model_validate(obj=self.config.spec.model_dump())

        manager_agent_base = await self.base_agent_builder.build_agent(
            spec.manager_agent
        )
        self.manager_agent = ManagerAgent(
            agent=manager_agent_base, gateway=self.agent_gateway
        )
        self.max_rounds = spec.max_rounds
        self.task_executor = TaskExecutor(self.task_agents)

    async def invoke(
        self, chat_history: BaseMultiModalInput, request: str
    ) -> AsyncIterable:
        session_id: str
        if chat_history.session_id:
            session_id = chat_history.session_id
        else:
            session_id = uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        source = f"{self.config.service_name}:{self.config.version}"

        with (
            self.t.tracer.start_as_current_span(
                name="invoke-sse", attributes={"goal": request}
            )
            if self.t.telemetry_enabled()
            else nullcontext()
        ):
            round_no = 0
            conversation = Conversation(messages=[])
            while True:
                with (
                    self.t.tracer.start_as_current_span(name="determine-next-action")
                    if self.t.telemetry_enabled()
                    else nullcontext()
                ):
                    try:
                        manager_output = await self.manager_agent.determine_next_action(
                            chat_history,
                            request,
                            self.task_agents_bases,
                            conversation.messages,
                        )
                    except Exception as e:
                        yield new_event_response(
                            EventType.ERROR,
                            ErrorResponse(
                                session_id=session_id,
                                source=source,
                                request_id=request_id,
                                status_code=500,
                                detail=str(e),
                            ),
                        )
                        return
                    manager_output.session_id = session_id
                    manager_output.source = source
                    manager_output.request_id = request_id
                    yield new_event_response(EventType.MANAGER_RESPONSE, manager_output)

                    match manager_output.next_action:
                        case Action.PROVIDE_RESULT:
                            yield new_event_response(
                                EventType.FINAL_RESPONSE,
                                InvokeResponse(
                                    session_id=session_id,
                                    source=source,
                                    request_id=request_id,
                                    token_usage=TokenUsage(
                                        completion_tokens=0,
                                        prompt_tokens=0,
                                        total_tokens=0,
                                    ),
                                    output_raw=conversation.get_message_by_task_id(
                                        manager_output.action_detail.result_task_id
                                    ).result,
                                ),
                            )
                            break
                        case Action.ABORT:
                            yield new_event_response(
                                EventType.ERROR,
                                AbortResult(
                                    session_id=session_id,
                                    source=source,
                                    request_id=request_id,
                                    abort_reason=manager_output.action_detail.abort_reason,
                                ),
                            )
                            break
                        case Action.ASSIGN_NEW_TASK:
                            async for result in self._execute_task(
                                manager_output.action_detail.task_id,
                                manager_output.action_detail.instructions,
                                manager_output.action_detail.agent_name,
                                conversation,
                            ):
                                yield result
                        case _:
                            yield new_event_response(
                                EventType.ERROR,
                                ErrorResponse(
                                    session_id=session_id,
                                    source=source,
                                    request_id=request_id,
                                    status_code=400,
                                    detail=f"Unknown action: {manager_output.next_action}",
                                ),
                            )
                            break
                    round_no = round_no + 1
                    if round_no >= self.max_rounds:
                        yield new_event_response(
                            EventType.ERROR,
                            AbortResult(
                                session_id=session_id,
                                source=source,
                                request_id=request_id,
                                abort_reason=f"Max rounds surpassed: {self.max_rounds}",
                            ),
                        )
