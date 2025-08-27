from contextlib import nullcontext

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader
from ska_utils import get_telemetry

from context_directive import parse_context_directives
from jose_types import ExtraData
from model.requests import ConversationMessageRequest

from .deps import (
    get_agent_catalog,
    get_config,
    get_conn_manager,
    get_conv_manager,
    get_fallback_agent,
    get_rec_chooser,
    get_user_context_cache,
)

conv_manager = get_conv_manager()
conn_manager = get_conn_manager()
rec_chooser = get_rec_chooser()
config = get_config()
agent_catalog = get_agent_catalog()
fallback_agent = get_fallback_agent()
cache_user_context = get_user_context_cache()

router = APIRouter()
header_scheme = APIKeyHeader(name="authorization", auto_error=False)


@router.get(
    "/conversations/{conversation_id}/messages",
    tags=["Conversations"],
    description="Get the full conversation history based on a session id.",
)
async def get_conversation_by_id(user_id: str, conversation_id: str):
    try:
        conv = await conv_manager.get_conversation(user_id, conversation_id)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to get conversation with conversation_id: {conversation_id} --- {e}",
        ) from e

    return {"conversation": conv}


@router.post(
    "/conversations/{conversation_id}/messages",
    tags=["Conversations"],
    description="Add a message to a conversation based on a session id.",
)
async def add_conversation_message_by_id(
    user_id: str,
    conversation_id: str,
    request: ConversationMessageRequest,
    authorization: str = Depends(header_scheme),
):
    jt = get_telemetry()

    try:
        conv = await conv_manager.get_conversation(user_id, conversation_id)
    except Exception as e:
        raise HTTPException(
            status_code=404,
            detail=f"Unable to get conversation with conversation_id: {conversation_id} --- {e}",
        ) from e

    in_memory_user_context = None
    if cache_user_context:
        in_memory_user_context = cache_user_context.get_user_context_from_cache(
            user_id=user_id
        ).model_dump()["user_context"]
        await conv_manager.add_transient_context(conv, in_memory_user_context)
    with (
        jt.tracer.start_as_current_span(
            name="conversation-turn",
            attributes={
                    "prompt": request.message,
                    "user_id": user_id,
                }
        )
        if jt.telemetry_enabled()
        else nullcontext()
    ):
        with (
            jt.tracer.start_as_current_span(
                name="choose-recipient",
                attributes={
                    "prompt": request.message
                }
            )
            if jt.telemetry_enabled()
            else nullcontext()
        ) as recipient_span:
            # Select an agent
            try:
                selected_agent = await rec_chooser.choose_recipient(request.message, conv)
                recipient_span.add_event(
                    "agent.selected",
                    attributes={"agent_name": selected_agent.agent_name}
                )
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error retrieving agent to handle conversation message --- {e}",
                ) from e

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
            try:
                await conv_manager.add_user_message(conv, request.message, sel_agent_name)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error adding new message to conversation history --- {e}",
                ) from e

        with (
            jt.tracer.start_as_current_span(
                name="agent-response",
                attributes={
                    "prompt": request.message,
                    "user_id": user_id,
                },
            )
            if jt.telemetry_enabled()
            else nullcontext()
        ) as span:
            response = agent.invoke_api(conv, authorization)
            token_usage = response.get("token_usage")
            if token_usage:
                span.set_attribute("completion_tokens", token_usage.get("completion_token", 0))
                span.set_attribute("prompt_tokens", token_usage.get("prompt_tokens", 0))
                span.set_attribute("total_tokens", token_usage.get("total_tokens", 0))
            try:
                # Set the agent response from raw output
                agent_response = response.get("output_raw", "No output available.")
                # Check for extra data and process it
                extra_data = response.get("extra_data")
                if extra_data is not None:
                    extra_data_instance = ExtraData.new_from_json(extra_data)
                    context_directives = parse_context_directives(extra_data_instance)
                    await conv_manager.process_context_directives(conv, context_directives)

            except Exception as e:
                print(f"Error processing extra data: {e}")
                # Fallback to printing output_raw again if an error occurs
                agent_response = response.get("output_raw", "No output available.")
                print(agent_response)

        with (
            jt.tracer.start_as_current_span("update-history-assistant")
            if jt.telemetry_enabled()
            else nullcontext()
        ):
            # Add response to conversation history
            try:
                await conv_manager.add_agent_message(conv, agent_response, sel_agent_name)
            except Exception as e:
                raise HTTPException(
                    status_code=500,
                    detail=f"Error adding response to conversation history --- {e}",
                ) from e
        conversation_result = await conv_manager.get_last_response(conv)
    return {"conversation": conversation_result}


@router.post(
    "/conversations",
    tags=["Conversations"],
    description="Start a new conversation. Returns new session ID and agent response.",
)
async def new_conversation(user_id: str):
    jt = get_telemetry()
    with (
        jt.tracer.start_as_current_span("init-conversation")
        if jt.telemetry_enabled()
        else nullcontext()
    ):
        try:
            conv = await conv_manager.new_conversation(user_id, False)
        except Exception as e:
            raise HTTPException(
                status_code=500, detail=f"Error creating new conversation --- {e}"
            ) from e

    return {"conversation_id": conv.conversation_id, "user_id": conv.user_id}


@router.get(
    "/healthcheck",
    tags=["Health"],
    description="Check the health status of Assistant Orchestrator.",
)
async def healthcheck():
    return {"status": "healthy"}
