import logging
import os
from contextlib import nullcontext
from typing import Any

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from opentelemetry.propagate import extract
from pydantic_yaml import parse_yaml_file_as
from ska_utils import AppConfig, get_telemetry, initialize_telemetry

from sk_agents.configs import (
    TA_PLUGIN_MODULE,
    TA_SERVICE_CONFIG,
    TA_TYPES_MODULE,
    configs,
)
from sk_agents.middleware import TelemetryMiddleware
from sk_agents.plugin_loader import get_plugin_loader
from sk_agents.ska_types import BaseHandler, Config, InvokeResponse
from sk_agents.skagents import handle as skagents_handle
from sk_agents.type_loader import get_type_loader


def docstring_parameter(*sub):
    def dec(obj):
        obj.__doc__ = obj.__doc__.format(*sub)
        return obj

    return dec


logging.basicConfig(level=logging.INFO)

AppConfig.add_configs(configs)
app_config = AppConfig()

config_file = app_config.get(TA_SERVICE_CONFIG.env_name)
config: Config = parse_yaml_file_as(Config, config_file)

agents_path = str(os.path.dirname(config_file))

types_module = app_config.get(TA_TYPES_MODULE.env_name)
# If no types module has been defined:
# Check if there is a custom_types.py file in the agents directory
if types_module is None:
    custom_types = os.path.join(agents_path, "custom_types.py")
    if os.path.exists(custom_types):
        app_config.props[TA_TYPES_MODULE.env_name] = custom_types
        types_module = custom_types
type_loader = get_type_loader(types_module)

plugin_module = app_config.get(TA_PLUGIN_MODULE.env_name)
# If no plugin module has been defined:
# Check if there is a custom_plugins.py file in the agents directory
if plugin_module is None:
    custom_plugins = os.path.join(agents_path, "custom_plugins.py")
    if os.path.exists(custom_plugins):
        app_config.props[TA_PLUGIN_MODULE.env_name] = custom_plugins
        plugin_module = custom_plugins
plugin_loader = get_plugin_loader(plugin_module)

initialize_telemetry(f"{config.service_name}-{config.version}", app_config)

root_handler = config.apiVersion.split("/")[0]

input_class = type_loader.get_type(config.input_type)

output_class = Any
if config.output_type is not None:
    output_class = type_loader.get_type(config.output_type)

if config.description is not None:
    description = config.description
else:
    description = f"{config.service_name} API"

app = FastAPI(
    openapi_url=f"/{config.service_name}/{str(config.version)}/openapi.json",
    docs_url=f"/{config.service_name}/{str(config.version)}/docs",
    redoc_url=f"/{config.service_name}/{str(config.version)}/redoc",
)
# noinspection PyTypeChecker
app.add_middleware(TelemetryMiddleware, st=get_telemetry())


@app.post(f"/{config.service_name}/{str(config.version)}")
@docstring_parameter(description)
async def invoke(inputs: input_class, request: Request) -> InvokeResponse[output_class]:  # type: ignore
    """
    {0}
    """
    st = get_telemetry()
    context = extract(request.headers)

    authorization = request.headers.get("authorization", None)
    with (
        st.tracer.start_as_current_span(
            f"{config.service_name}-{str(config.version)}-invoke", context=context
        )
        if st.telemetry_enabled()
        else nullcontext()
    ):
        match root_handler:
            case "skagents":
                handler: BaseHandler = skagents_handle(config, app_config, authorization)
            case _:
                raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

        inv_inputs = inputs.__dict__
        output = await handler.invoke(inputs=inv_inputs)
        return output


@app.websocket(f"/{config.service_name}/{str(config.version)}/stream")
async def invoke_stream(websocket: WebSocket) -> None:
    await websocket.accept()
    st = get_telemetry()
    context = extract(websocket.headers)

    authorization = websocket.headers.get("authorization", None)
    try:
        data = await websocket.receive_json()
        with (
            st.tracer.start_as_current_span(
                f"{config.service_name}-{str(config.version)}-invoke_stream",
                context=context,
            )
            if st.telemetry_enabled()
            else nullcontext()
        ):
            inputs: input_class = input_class(**data)
            inv_inputs = inputs.__dict__
            match root_handler:
                case "skagents":
                    handler: BaseHandler = skagents_handle(config, app_config, authorization)
                    async for content in handler.invoke_stream(inputs=inv_inputs):
                        await websocket.send_text(content)
                    await websocket.close()
                case _:
                    raise ValueError(f"Unknown apiVersion: {config.apiVersion}")
    except WebSocketDisconnect:
        print("websocket disconnected")
