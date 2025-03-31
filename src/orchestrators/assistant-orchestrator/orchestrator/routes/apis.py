from .deps import (
    get_conv_manager,
    get_conn_manager,
    get_rec_chooser,
    get_config,
    get_agent_catalog,
    get_fallback_agent,
    get_user_context_cache
)
from contextlib import nullcontext
from fastapi import Depends, APIRouter
from fastapi.security import APIKeyHeader
from ska_utils import get_telemetry
from jose_types import ExtraData
from context_directive import parse_context_directives
from model.requests import ConversationMessageRequest

conv_manager = get_conv_manager()
conn_manager = get_conn_manager()
rec_chooser = get_rec_chooser()
config = get_config()
agent_catalog = get_agent_catalog()
fallback_agent = get_fallback_agent()
cache_user_context = get_user_context_cache()

router = APIRouter()
header_scheme = APIKeyHeader(name="authorization", auto_error=False)

@router.get("/conversations/{session_id}", tags=["Conversations"],
         description="Get the full conversation history based on a session id.")
async def get_conversation_by_id(user_id: str, session_id: str):
    conv = conv_manager.get_conversation(user_id, session_id)
    return {"conversation": conv}

@router.put("/conversations/{session_id}", tags=["Conversations"],
             description="Add a message to a conversation based on a session id.")
async def add_conversation_message_by_id(
    user_id: str,
    session_id: str,
    request: ConversationMessageRequest,
    authorization: str = Depends(header_scheme)
):
    jt = get_telemetry()
    in_memory_user_context = None
    if cache_user_context:
        in_memory_user_context = cache_user_context.get_user_context_from_cache(user_id=user_id).model_dump()['user_context'] 
    conv = conv_manager.get_conversation(user_id, session_id, transient_user_context=in_memory_user_context)

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
            # Select an agent
            selected_agent = await rec_chooser.choose_recipient(request.message, conv)
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
            conv_manager.add_user_message(conv, request.message, sel_agent_name)

        with (
            jt.tracer.start_as_current_span("agent-response")
            if jt.telemetry_enabled()
            else nullcontext()
        ):
            response = agent.invoke_api(conv, authorization)
            try:
                # Set the agent response from raw output
                agent_response = response.get('output_raw', "No output available.")
                # Check for extra data and process it
                extra_data = response.get('extra_data')
                if extra_data is not None:
                    extra_data_instance = ExtraData.new_from_json(extra_data)
                    context_directives = parse_context_directives(extra_data_instance)
                    conv_manager.process_context_directives(conv, context_directives)

            except Exception as e:
                print(f"Error processing extra data: {e}")
                # Fallback to printing output_raw again if an error occurs
                agent_response = response.get('output_raw', "No output available.")
                print(agent_response)

        with (
            jt.tracer.start_as_current_span("update-history-assistant")
            if jt.telemetry_enabled()
            else nullcontext()
        ):
            # Add response to conversation history
            conv_manager.add_agent_message(conv, agent_response, sel_agent_name)
        
    return {"conversation": conv_manager.get_last_response(conv) }

@router.post("/conversation/new_conversation", tags=["Conversations"],
         description="Start a new conversation. Returns new session ID and agent response.")
async def new_conversation(user_id: str, is_resumed: bool):
    jt = get_telemetry()
    with (
        jt.tracer.start_as_current_span("init-conversation")
        if jt.telemetry_enabled()
        else nullcontext()
    ):
        conv = conv_manager.new_conversation(user_id, is_resumed)
    return {"conversation": conv}

@router.get("/healthcheck", tags=["Health"],
         description="Check the health status of the application.")
async def healthcheck():
    return {"status": "healthy"}