from contextlib import nullcontext

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import StreamingResponse
from opentelemetry.propagate import extract
from redis import Redis
from ska_utils import AppConfig, get_telemetry, RedisStreamsEventPublisher

from sk_agents.a2a_types import A2AInvokeEvent, A2AInvokeResponse, A2AEventType
from sk_agents.configs import TA_REDIS_HOST, TA_REDIS_PORT
from sk_agents.ska_types import (
    BaseConfig,
    BaseHandler,
    InvokeResponse,
    PartialResponse,
)
from sk_agents.skagents import handle as skagents_handle
from sk_agents.utils import docstring_parameter, get_sse_event_for_response


class Routes:
    @staticmethod
    def get_rest_routes(
        name: str,
        version: str,
        description: str,
        root_handler_name: str,
        config: BaseConfig,
        app_config: AppConfig,
        input_class: type,
        output_class: type,
    ) -> APIRouter:
        router = APIRouter()

        @router.post("")
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
                    f"{name}-{version}-invoke",
                    context=context,
                )
                if st.telemetry_enabled()
                else nullcontext()
            ):
                match root_handler_name:
                    case "skagents":
                        handler: BaseHandler = skagents_handle(
                            config, app_config, authorization
                        )
                    case _:
                        raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

                inv_inputs = inputs.__dict__
                output = await handler.invoke(inputs=inv_inputs)
                return output

        @router.post("/sse")
        @docstring_parameter(description)
        async def invoke_sse(
            inputs: input_class, request: Request
        ) -> StreamingResponse:
            """
            Stream data to the client using Server-Sent Events (SSE).
            """
            st = get_telemetry()
            context = extract(request.headers)
            authorization = request.headers.get("authorization", None)
            inv_inputs = inputs.__dict__

            async def event_generator():
                with (
                    st.tracer.start_as_current_span(
                        f"{config.service_name}-{str(config.version)}-invoke_sse",
                        context=context,
                    )
                    if st.telemetry_enabled()
                    else nullcontext()
                ):
                    match root_handler_name:
                        case "skagents":
                            handler: BaseHandler = skagents_handle(
                                config, app_config, authorization
                            )
                            # noinspection PyTypeChecker
                            async for content in handler.invoke_stream(
                                inputs=inv_inputs
                            ):
                                yield get_sse_event_for_response(content)
                        case _:
                            raise ValueError(f"Unknown apiVersion: {config.apiVersion}")

            return StreamingResponse(event_generator(), media_type="text/event-stream")

        return router

    @staticmethod
    def get_a2a_rest_routes(
        name: str, version: str, app_config: AppConfig
    ) -> APIRouter:
        router = APIRouter()

        def _assert_valid_event(a2a_event: A2AInvokeEvent) -> None:
            if not a2a_event.event_id:
                raise HTTPException(
                    status_code=400, detail="Invalid event data - Missing event_id"
                )
            if not a2a_event.event_type or (
                a2a_event.event_type != A2AEventType.INVOKE
                and a2a_event.event_type != A2AEventType.INVOKE_STREAM
            ):
                raise HTTPException(
                    status_code=400, detail="Invalid event data - Invalid event_type"
                )

        @router.post("/a2a")
        async def invoke_a2a(a2a_event: A2AInvokeEvent) -> A2AInvokeResponse:
            _assert_valid_event(a2a_event)

            publisher = RedisStreamsEventPublisher(
                r=Redis(
                    host=app_config.get(TA_REDIS_HOST.env_name),
                    port=int(app_config.get(TA_REDIS_PORT.env_name)),
                )
            )
            try:
                publisher.publish_event(
                    topic_name=f"{name}/{version}",
                    event_data=a2a_event.model_dump_json(),
                )
                return A2AInvokeResponse(
                    event_id=a2a_event.event_id,
                    topic=f"{name}/{version}/{a2a_event.event_id}",
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to publish event: {str(e)}",
                )

        return router

    @staticmethod
    def get_websocket_routes(
        name: str,
        version: str,
        root_handler_name: str,
        config: BaseConfig,
        app_config: AppConfig,
        input_class: type,
    ) -> APIRouter:
        router = APIRouter()

        @router.websocket("/stream")
        async def invoke_stream(websocket: WebSocket) -> None:
            await websocket.accept()
            st = get_telemetry()
            context = extract(websocket.headers)

            authorization = websocket.headers.get("authorization", None)
            try:
                data = await websocket.receive_json()
                with (
                    st.tracer.start_as_current_span(
                        f"{name}-{str(version)}-invoke_stream",
                        context=context,
                    )
                    if st.telemetry_enabled()
                    else nullcontext()
                ):
                    inputs: input_class = input_class(**data)
                    inv_inputs = inputs.__dict__
                    match root_handler_name:
                        case "skagents":
                            handler: BaseHandler = skagents_handle(
                                config, app_config, authorization
                            )
                            # noinspection PyTypeChecker
                            async for content in handler.invoke_stream(
                                inputs=inv_inputs
                            ):
                                if isinstance(content, PartialResponse):
                                    await websocket.send_text(content.output_partial)
                            await websocket.close()
                        case _:
                            raise ValueError(f"Unknown apiVersion: {config.apiVersion}")
            except WebSocketDisconnect:
                print("websocket disconnected")

        return router
