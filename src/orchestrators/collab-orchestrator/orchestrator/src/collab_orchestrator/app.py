import logging
import uuid
from collections.abc import AsyncIterable
from contextlib import nullcontext
from copy import deepcopy

import redis.asyncio as redis  # ➊ NEW
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from opentelemetry.propagate import Context, extract
from pydantic_yaml import parse_yaml_file_as
from ska_utils import AppConfig, get_telemetry, initialize_telemetry, strtobool

from collab_orchestrator.agents import (
    AgentGateway,
    BaseAgent,
    BaseAgentBuilder,
    TaskAgent,
)
from collab_orchestrator.co_types import BaseConfig, BaseMultiModalInput, KindHandler
from collab_orchestrator.configs import (
    CONFIGS,
    TA_AGW_HOST,
    TA_AGW_KEY,
    TA_AGW_SECURE,
    TA_REDIS_DB,  # ➋ NEW
    TA_REDIS_HOST,  # ➋
    TA_REDIS_PORT,  # ➋
    TA_SERVICE_CONFIG,
)
from collab_orchestrator.handler_factory import HandlerFactory
from collab_orchestrator.planning_handler.pending_plans import PendingPlanStore  # ➌
from collab_orchestrator.planning_handler.plan import Plan  # ➌

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------- helpers
def docstring_parameter(*sub):
    def dec(obj):
        obj.__doc__ = obj.__doc__.format(*sub)
        return obj

    return dec


# ----------------------------------------------------------------- config / telemetry
AppConfig.add_configs(CONFIGS)
app_config = AppConfig()

config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
config: BaseConfig = parse_yaml_file_as(BaseConfig, config_file)

if config.apiVersion != "skagents/v1":
    raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

if config.description:
    description = config.description
else:
    description = f"{config.service_name} {config.version}"

initialize_telemetry(config.service_name, app_config)
t = get_telemetry()

# ----------------------------------------------------------------- globals
agent_gateway: AgentGateway
base_agent_builder: BaseAgentBuilder
task_agents_bases: list[BaseAgent] = []
task_agents: list[TaskAgent] = []
handler: KindHandler

# HITL flag & Redis store
hitl_enabled = bool(getattr(config.spec, "human_in_the_loop", False))
plan_store: PendingPlanStore | None = PendingPlanStore() if hitl_enabled else None

# Browser session cache (unchanged)
session_cache: dict[str, BaseMultiModalInput] = {}


# ----------------------------------------------------------------- startup
async def initialize():
    global agent_gateway, base_agent_builder, task_agents_bases, task_agents, handler

    with (
        t.tracer.start_as_current_span("initialization") if t.telemetry_enabled() else nullcontext()
    ):
        # --- fail fast if HITL requested but Redis unreachable
        if hitl_enabled:
            try:
                r = redis.Redis(
                    host=app_config.get(TA_REDIS_HOST.env_name) or "localhost",
                    port=int(app_config.get(TA_REDIS_PORT.env_name) or 6379),
                    db=int(app_config.get(TA_REDIS_DB.env_name) or 0),
                    decode_responses=True,
                )
                await r.ping()
            except Exception as e:
                raise RuntimeError(f"HITL enabled but Redis unreachable: {e}") from e

        agent_gateway = AgentGateway(
            host=app_config.get(TA_AGW_HOST.env_name),
            secure=strtobool(app_config.get(TA_AGW_SECURE.env_name)),
            agw_key=app_config.get(TA_AGW_KEY.env_name),
        )
        base_agent_builder = BaseAgentBuilder(gateway=agent_gateway)

        for task_agent_name in config.spec.agents:
            task_agent_base = await base_agent_builder.build_agent(task_agent_name)
            task_agents_bases.append(task_agent_base)

            task_agent = TaskAgent(agent=task_agent_base, gateway=agent_gateway)
            task_agents.append(task_agent)

        handler_factory = HandlerFactory(
            t,
            config,
            agent_gateway,
            base_agent_builder,
            task_agents_bases,
            task_agents,
        )
        if not handler_factory.is_valid_handler(config.kind):
            raise ValueError(f"Unknown kind: {config.kind}")

        handler = handler_factory.get_handler(config.kind)
        await handler.initialize()


# ----------------------------------------------------------------- FastAPI app
app = FastAPI(
    openapi_url=f"/{config.service_name}/{config.version}/openapi.json",
    docs_url=f"/{config.service_name}/{config.version}/docs",
    redoc_url=f"/{config.service_name}/{config.version}/redoc",
)
app.add_event_handler("startup", initialize)


# ----------------------------------------------------------------- helper to run handler in a span
async def invoke_with_span(
    context: Context, chat_history: BaseMultiModalInput, request: str
) -> AsyncIterable:
    with (
        t.tracer.start_as_current_span(name="invoke-sse", context=context)
        if t.telemetry_enabled()
        else nullcontext()
    ):
        async for event in handler.invoke(chat_history, request):
            yield event


# ----------------------------------------------------------------- endpoints
@app.post(f"/{config.service_name}/{config.version}")
@docstring_parameter(description)
async def invoke():
    """
    {0}

    """
    return {"message": "This is a non-functional endpoint"}


# ----------- SSE (non-browser) ------------------------------------------------
@app.post(f"/{config.service_name}/{config.version}/sse")
@docstring_parameter(description)
async def invoke_sse(chat_history: BaseMultiModalInput, request: Request):
    """
    {0}

    """
    context = extract(request.headers)
    if not chat_history:
        raise HTTPException(status_code=400, detail="Chat history is required")
    if chat_history.chat_history[-1].role != "user":
        raise HTTPException(status_code=400, detail="First message must be from user")

    if not chat_history.session_id:
        chat_history.session_id = uuid.uuid4().hex

    request = chat_history.chat_history.pop()

    return StreamingResponse(
        invoke_with_span(context, chat_history, request.items[-1].content),
        media_type="text/event-stream",
    )


# ----------- Browser helper pair --------------------------------------------
@app.post(f"/{config.service_name}/{config.version}/browser")
@docstring_parameter(description)
async def invoke_browser(chat_history: BaseMultiModalInput):
    """
    {0}

    Initiate a session for a browser - Since EventSource only supports GET calls
    and for the agent/orchestrator to work it needs input, call this endpoint
    first to create a session and then call the GET endpoint with the session ID.
    """

    if not chat_history:
        raise HTTPException(status_code=400, detail="Chat history is required")
    if chat_history.chat_history[-1].role != "user":
        raise HTTPException(status_code=400, detail="First message must be from user")

    session_id: str
    if chat_history.session_id:
        session_id = chat_history.session_id
    else:
        session_id = str(uuid.uuid4().hex)
        chat_history.session_id = session_id
    session_cache[session_id] = chat_history

    return {"session_id": session_id}


@app.get(f"/{config.service_name}/{config.version}/browser/{{session_id}}")
@docstring_parameter(description)
async def get_browser_response(session_id: str, request: Request):
    """
    {0}

    Execute a session for a browser - Using the previously established session
    ID (via the POST browser endpoint), use this endpoint with EventSource to
    receive the SSE event stream in a browser.
    """

    context = extract(request.headers)
    with (
        t.tracer.start_as_current_span(name="invoke-sse", context=context)
        if t.telemetry_enabled()
        else nullcontext()
    ):
        if not session_id:
            raise HTTPException(status_code=400, detail="Session ID is required")
        if session_id not in session_cache:
            raise HTTPException(status_code=400, detail="Session ID not found")

        chat_history = deepcopy(session_cache[session_id])
        request = chat_history.chat_history.pop()

        return StreamingResponse(
            invoke_with_span(context, chat_history, request.items[-1].content),
            media_type="text/event-stream",
        )


# ----------- HITL decision routes (added only if enabled) --------------------
if hitl_enabled:
    base = f"/{config.service_name}/{config.version}/sse"

    @app.post(f"{base}/{{session_id}}/approve")
    async def approve_plan(session_id: str):
        await plan_store.set_decision(session_id, "approve")
        return {"status": "Plan approved"}

    @app.post(f"{base}/{{session_id}}/cancel")
    async def cancel_plan(session_id: str):
        await plan_store.set_decision(session_id, "cancel")
        return {"status": "Plan cancelled"}

    @app.post(f"{base}/{{session_id}}/edit")
    async def edit_plan(session_id: str, edited_plan: Plan):
        await plan_store.set_decision(session_id, "edit", edited_plan.model_dump())
        return {"status": "Plan modified and accepted"}
