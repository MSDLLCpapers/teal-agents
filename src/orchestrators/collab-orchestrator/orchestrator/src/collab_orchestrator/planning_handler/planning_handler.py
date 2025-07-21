import uuid
from collections.abc import AsyncIterable
from contextlib import nullcontext

from ska_utils import Telemetry

from collab_orchestrator.agents import (
    AgentGateway,
    BaseAgent,
    BaseAgentBuilder,
    TaskAgent,
)
from collab_orchestrator.co_types import (
    AbortResult,
    BaseConfig,
    BaseMultiModalInput,
    ErrorResponse,
    EventType,
    InvokeResponse,
    KindHandler,
    TokenUsage,
    new_event_response,
)
from collab_orchestrator.planning_handler.pending_plans import PendingPlanStore  # HITL support
from collab_orchestrator.planning_handler.plan_manager import (
    PlanManager,
    PlanningFailedException,
)
from collab_orchestrator.planning_handler.planning_agent import PlanningAgent
from collab_orchestrator.planning_handler.step_executor import StepExecutor
from collab_orchestrator.planning_handler.types import PlanningSpec


class PlanningHandler(KindHandler):
    def __init__(
        self,
        t: Telemetry,
        config: BaseConfig,
        agent_gateway: AgentGateway,
        base_agent_builder: BaseAgentBuilder,
        task_agents_bases: list[BaseAgent],
        task_agents: list[TaskAgent],
    ):
        super().__init__(
            t, config, agent_gateway, base_agent_builder, task_agents_bases, task_agents
        )
        self.plan_manager = None
        self.planning_agent = None
        self.stream_tokens = False
        # Begin HITL support
        self.hitl = bool(getattr(config.spec, "human_in_the_loop", False))
        self.timeout = int(getattr(config.spec, "hitl_timeout", 0) or 0)
        self.store = PendingPlanStore() if self.hitl else None
        # End HITL support

    def _start_span(self, name: str, attributes: dict | None = None):
        if self.t.telemetry_enabled():
            return self.t.tracer.start_as_current_span(name=name, attributes=attributes)
        return nullcontext()

    async def initialize(self):
        spec: PlanningSpec = PlanningSpec.model_validate(obj=self.config.spec.model_dump())

        planning_agent_base = await self.base_agent_builder.build_agent(spec.planning_agent)
        self.planning_agent = PlanningAgent(agent=planning_agent_base, gateway=self.agent_gateway)
        self.plan_manager = PlanManager(self.planning_agent)
        self.stream_tokens = spec.stream_tokens

    async def invoke(self, chat_history: BaseMultiModalInput, request: str) -> AsyncIterable:
        session_id: str
        if chat_history.session_id:
            session_id = chat_history.session_id
        else:
            session_id = uuid.uuid4().hex
        request_id = uuid.uuid4().hex
        source = f"{self.config.service_name}:{self.config.version}"

        with self._start_span(name="invoke-sse", attributes={"goal": request}):
            with self._start_span(name="build-plan"):
                try:
                    plan = await self.plan_manager.generate_plan(
                        chat_history=chat_history,
                        overall_goal=request,
                        task_agents=self.task_agents_bases,
                    )
                except PlanningFailedException as e:
                    yield new_event_response(
                        EventType.ERROR,
                        AbortResult(
                            session_id=session_id,
                            source=source,
                            request_id=request_id,
                            abort_reason=e.args[0],
                        ),
                    )
                    return
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
                plan.session_id = session_id
                plan.source = source
                plan.request_id = request_id
                yield new_event_response(EventType.PLAN, plan)

                # Begin HITL support: pause if HITL enabled
                if self.hitl:
                    await self.store.save(session_id, plan.model_dump())
                    stored = await self.store.wait_for_decision(session_id, self.timeout)
                    if not stored:
                        yield new_event_response(
                            EventType.ERROR,
                            AbortResult(
                                session_id=session_id,
                                source=source,
                                request_id=request_id,
                                abort_reason="Plan approval timed out.",
                            ),
                        )
                        return
                    if stored["status"] == "cancel":
                        await self.store.delete(session_id)
                        yield new_event_response(
                            EventType.ERROR,
                            AbortResult(
                                session_id=session_id,
                                source=source,
                                request_id=request_id,
                                abort_reason="Plan execution cancelled by user.",
                            ),
                        )
                        return
                    if stored["status"] == "edit":
                        # Convert edited plan dict back to Plan object
                        from collab_orchestrator.planning_handler.plan import Plan

                        plan = Plan.model_validate(stored["edited_plan"])
                    await self.store.delete(session_id)
                # End HITL support

            with self._start_span(name="execute-plan"):
                step_executor = StepExecutor(self.task_agents)
                for step in plan.steps:
                    try:
                        if self.stream_tokens:
                            async for result in step_executor.execute_step_sse(
                                session_id, source, request_id, step
                            ):
                                yield result
                        else:
                            async for result in step_executor.execute_step(
                                session_id, source, request_id, step
                            ):
                                yield result
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

            yield new_event_response(
                EventType.FINAL_RESPONSE,
                InvokeResponse(
                    session_id=session_id,
                    source=source,
                    request_id=request_id,
                    token_usage=TokenUsage(completion_tokens=0, prompt_tokens=0, total_tokens=0),
                    output_raw=plan.steps[-1].step_tasks[0].result,
                ),
            )
