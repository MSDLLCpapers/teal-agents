from contextlib import nullcontext

import logging

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from ska_utils import get_telemetry

from agents import AgentConnectionError, AgentTimeoutError, AgentResponseError, AgentInvalidResponseError
from context_directive import parse_context_directives
from jose_types import ExtraData

logger = logging.getLogger(__name__)

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
        conv = await conv_manager.new_conversation(user_id, is_resumed=is_resumed)

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
                    try:
                        selected_agent = await rec_chooser.choose_recipient(
                            message, conv, authorization
                        )
                    except AgentConnectionError as e:
                        logger.error(f"Agent selector service is unreachable: {e}")
                        await websocket.send_json({
                            "error": True,
                            "error_type": "agent_selector_unavailable",
                            "message": f"Agent selector service '{e.agent_name}' is not available. The service may be down or unreachable.",
                        })
                        continue
                    except AgentTimeoutError as e:
                        logger.error(f"Agent selector service timed out: {e}")
                        await websocket.send_json({
                            "error": True,
                            "error_type": "agent_selector_timeout",
                            "message": f"Agent selector service '{e.agent_name}' timed out while choosing a recipient.",
                        })
                        continue
                    except AgentResponseError as e:
                        logger.error(f"Agent selector service returned error: {e}")
                        if e.status_code == 401:
                            error_msg = f"Agent selector service '{e.agent_name}' authentication failed: {e.detail}"
                        elif e.status_code == 429:
                            error_msg = f"Agent selector service '{e.agent_name}' is rate limited. Please try again later."
                        else:
                            error_msg = f"Agent selector service '{e.agent_name}' returned an error (HTTP {e.status_code}): {e.detail}"
                        await websocket.send_json({
                            "error": True,
                            "error_type": "agent_selector_error",
                            "message": error_msg,
                        })
                        continue
                    except Exception as e:
                        logger.error(f"Error choosing recipient: {e}")
                        await websocket.send_json({
                            "error": True,
                            "error_type": "agent_selector_unavailable",
                            "message": f"Agent selector service encountered an error: {e}",
                        })
                        continue
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
                    await conv_manager.add_user_message(conv, message, sel_agent_name)

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
                    try:
                        async for content in agent.invoke_stream(conv, authorization=authorization):
                            try:
                                extra_data: ExtraData = ExtraData.new_from_json(content)
                                context_directives = parse_context_directives(extra_data)
                                await conv_manager.process_context_directives(conv, context_directives)
                            except Exception:
                                response = f"{response}{content}"
                                await websocket.send_text(content)
                    except AgentConnectionError as e:
                        logger.error(f"Agent unavailable during WebSocket streaming: {e}")
                        await websocket.send_json({
                            "error": True,
                            "error_type": "agent_unavailable",
                            "message": f"Agent '{sel_agent_name}' is not available. The agent may be down or unreachable.",
                        })
                        continue
                    except AgentTimeoutError as e:
                        logger.error(f"Agent timed out during WebSocket streaming: {e}")
                        await websocket.send_json({
                            "error": True,
                            "error_type": "agent_timeout",
                            "message": f"Agent '{sel_agent_name}' timed out while processing the request.",
                        })
                        continue
                    except AgentResponseError as e:
                        logger.error(f"Agent returned error during WebSocket streaming: {e}")
                        if e.status_code == 401:
                            error_msg = f"Agent '{sel_agent_name}' authentication failed: {e.detail}"
                        elif e.status_code == 429:
                            error_msg = f"Agent '{sel_agent_name}' is rate limited. Please try again later."
                        else:
                            error_msg = f"Agent '{sel_agent_name}' returned an error (HTTP {e.status_code}): {e.detail}"
                        await websocket.send_json({
                            "error": True,
                            "error_type": "agent_error",
                            "message": error_msg,
                        })
                        continue
                    except Exception as e:
                        logger.error(f"Unexpected error during agent streaming: {e}")
                        await websocket.send_json({
                            "error": True,
                            "error_type": "unknown_error",
                            "message": f"An unexpected error occurred while communicating with agent '{sel_agent_name}': {e}",
                        })
                        continue

                with (
                    jt.tracer.start_as_current_span("update-history-assistant")
                    if jt.telemetry_enabled()
                    else nullcontext()
                ):
                    # Add response to conversation history
                    await conv_manager.add_agent_message(conv, response, sel_agent_name)
    except WebSocketDisconnect:
        conn_manager.disconnect(websocket)
