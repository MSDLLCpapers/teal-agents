import uuid
from contextlib import nullcontext
from copy import deepcopy
from typing import List, Dict

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic_yaml import parse_yaml_file_as
from ska_utils import AppConfig, strtobool, initialize_telemetry, get_telemetry

from collab_orchestrator.agents import (
    AgentGateway,
    BaseAgentBuilder,
    BaseAgent,
    TaskAgent,
)
from collab_orchestrator.co_types import BaseConfig, KindHandler
from collab_orchestrator.co_types.requests import BaseMultiModalInput
from collab_orchestrator.configs import (
    CONFIGS,
    TA_SERVICE_CONFIG,
    TA_AGW_HOST,
    TA_AGW_SECURE,
    TA_AGW_KEY,
)
from collab_orchestrator.handler_factory import HandlerFactory


def docstring_parameter(*sub):
    def dec(obj):
        obj.__doc__ = obj.__doc__.format(*sub)
        return obj

    return dec


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

agent_gateway: AgentGateway
base_agent_builder: BaseAgentBuilder
task_agents_bases: List[BaseAgent] = []
task_agents: List[TaskAgent] = []
handler: KindHandler


async def initialize():
    global agent_gateway, base_agent_builder, task_agents_bases, task_agents, handler

    with (
        t.tracer.start_as_current_span("initialization")
        if t.telemetry_enabled()
        else nullcontext()
    ):
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


app = FastAPI(
    openapi_url=f"/{config.service_name}/{config.version}/openapi.json",
    docs_url=f"/{config.service_name}/{config.version}/docs",
    redoc_url=f"/{config.service_name}/{config.version}/redoc",
)
app.add_event_handler("startup", initialize)

session_cache: Dict[str, BaseMultiModalInput] = {}


@app.post(f"/{config.service_name}/{config.version}")
@docstring_parameter(description)
async def invoke_sse():
    """
    {0}

    """
    return {"message": "This is a non-functional endpoint"}


@app.post(f"/{config.service_name}/{config.version}/sse")
@docstring_parameter(description)
async def invoke_sse(chat_history: BaseMultiModalInput):
    """
    {0}

    """

    if not chat_history:
        raise HTTPException(status_code=400, detail="Chat history is required")
    if chat_history.chat_history[-1].role != "user":
        raise HTTPException(status_code=400, detail="First message must be from user")

    if not chat_history.session_id:
        chat_history.session_id = uuid.uuid4().hex

    request = chat_history.chat_history.pop()

    return StreamingResponse(
        handler.invoke(chat_history, request.items[-1].content),
        media_type="text/event-stream",
    )


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
async def get_browser_response(session_id: str):
    """
    {0}

    Execute a session for a browser - Using the previously established session
    ID (via the POST browser endpoint), use this endpoint with EventSource to
    receive the SSE event stream in a browser.
    """

    if not session_id:
        raise HTTPException(status_code=400, detail="Session ID is required")
    if session_id not in session_cache:
        raise HTTPException(status_code=400, detail="Session ID not found")

    chat_history = deepcopy(session_cache[session_id])
    request = chat_history.chat_history.pop()

    return StreamingResponse(
        handler.invoke(chat_history, request.items[-1].content),
        media_type="text/event-stream",
    )
