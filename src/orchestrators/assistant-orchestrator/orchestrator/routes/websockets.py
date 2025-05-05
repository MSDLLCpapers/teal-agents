from contextlib import nullcontext

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from ska_utils import get_telemetry

from context_directive import parse_context_directives
from jose_types import ExtraData

from .deps import (
    get_agent_catalog,
    get_config,
    get_conn_manager,
    get_conv_manager,
    get_fallback_agent,
    get_rec_chooser,
)

conv_manager = get_conv_manager()
conn_manager = get_conn_manager()
rec_chooser = get_rec_chooser()
config = get_config()
agent_catalog = get_agent_catalog()
fallback_agent = get_fallback_agent()

router = APIRouter()


@router.websocket("/stream/{ticket}")
async def invoke_stream(
    websocket: WebSocket,
    ticket: str,
    resume: bool = False,
    authorization: str | None = None,
) -> None:
    jt = get_telemetry()
    with (
        jt.tracer.start_as_current_span("init-conversation")
        if jt.telemetry_enabled()
        else nullcontext()
    ):
        is_resumed = True if resume else False
        user_id = await conn_manager.connect(config.service_name, websocket, ticket)
        conv = conv_manager.new_conversation(user_id, is_resumed=is_resumed)

    try:
        while True:
            # Receive message from client
            message = await websocket.receive_text()

            with (
                jt.tracer.start_as_current_span("conversation-turn")
                if jt.telemetry_enabled()
                else nullcontext()
            ):
                with (
                    jt.tracer.start_as_current_span("choose-recipient")
                    if jt.telemetry_enabled()
                    else nullcontext()
                ):
                    selected_agent = await rec_chooser.choose_recipient(message, conv)
                    if selected_agent.agent_name not in agent_catalog.agents:
                        agent = fallback_agent
                        sel_agent_name = fallback_agent.name
                    else:
                        agent = agent_catalog.agents[selected_agent.agent_name]
                        sel_agent_name = agent.name

                with (
                    jt.tracer.start_as_current_span("update-history-user")
                    if jt.telemetry_enabled()
                    else nullcontext()
                ):
                    # Add the current message to conversation history
                    conv_manager.add_user_message(conv, message, sel_agent_name)

                # Notify the client of which agent
                # will be handling this message
                await websocket.send_json(
                    {
                        "agent_name": sel_agent_name,
                        "confidence": selected_agent.confidence,
                        "is_followup": selected_agent.is_followup,
                    }
                )

                with (
                    jt.tracer.start_as_current_span("stream-response")
                    if jt.telemetry_enabled()
                    else nullcontext()
                ):
                    # Stream agent response to client
                    response = ""
                    async for content in agent.invoke_stream(conv, authorization=authorization):
                        try:
                            extra_data: ExtraData = ExtraData.new_from_json(content)
                            context_directives = parse_context_directives(extra_data)
                            conv_manager.process_context_directives(conv, context_directives)
                        except Exception:
                            response = f"{response}{content}"
                            await websocket.send_text(content)

                with (
                    jt.tracer.start_as_current_span("update-history-assistant")
                    if jt.telemetry_enabled()
                    else nullcontext()
                ):
                    # Add response to conversation history
                    conv_manager.add_agent_message(conv, response, sel_agent_name)
    except WebSocketDisconnect:
        conn_manager.disconnect(websocket)
