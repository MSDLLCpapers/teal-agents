
import logging

from contextlib import nullcontext

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from ska_utils import AppConfig, get_telemetry

from context_directive import parse_context_directives
from jose_types import ExtraData
from configs import TA_ENABLE_PARALLEL_PROCESSING
from integration.celery_client import app
from .deps import (
    get_agent_catalog,
    get_config,
    get_conn_manager,
    get_conv_manager,
    get_fallback_agent,
    get_rec_chooser,
    get_orchestration_service,
    get_tfidf_learning_service,
    get_postgres_client
)

logger = logging.getLogger(__name__)

conv_manager = get_conv_manager()
conn_manager = get_conn_manager()
rec_chooser = get_rec_chooser()
config = get_config()
agent_catalog = get_agent_catalog()
fallback_agent = get_fallback_agent()
postgres_client = get_postgres_client()
tfidf_service = get_tfidf_learning_service()

# Get orchestration service from deps
orchestration_service = get_orchestration_service()

# Load parallel processing configuration using AppConfig
app_config = AppConfig()
ENABLE_PARALLEL_PROCESSING = app_config.get(TA_ENABLE_PARALLEL_PROCESSING.env_name).lower() == "true"

# Log parallel processing configuration at startup
logger.info(f"WebSocket Parallel Processing: {'ENABLED' if ENABLE_PARALLEL_PROCESSING else 'DISABLED'}")

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
                    selected_agent = await rec_chooser.choose_recipient(message, conv, authorization)
                    logger.info(f"Agent selected: {selected_agent.agent_name} (parallel={selected_agent.is_parallel})")
                    
                    # Resolve agents using recipient chooser
                    agents_to_invoke, primary_agent_name = rec_chooser.resolve_agents(
                        selected_agent, agent_catalog, fallback_agent
                    )
                    
                    # Determine if parallel execution should happen
                    should_execute_parallel = (
                        ENABLE_PARALLEL_PROCESSING and 
                        len(agents_to_invoke) > 1
                    )
                    
                    # Set parallel flags for response
                    parallel_agents = [a.name for a in agents_to_invoke[1:]] if len(agents_to_invoke) > 1 else []
                    parallel_reason = selected_agent.confidence if len(agents_to_invoke) > 1 else ""

                with (
                    jt.tracer.start_as_current_span("update-history-user")
                    if jt.telemetry_enabled()
                    else nullcontext()
                ):
                    # Add the current message to conversation history
                    await conv_manager.add_user_message(conv, message, primary_agent_name)

                # Log the agent selection decision
                agent_names = ", ".join([a.name for a in agents_to_invoke])
                logger.info(f"Agent(s): {agent_names} (confidence={selected_agent.confidence}, followup={selected_agent.is_followup})")

                # Notify the client of which agent(s) will be handling this message
                await websocket.send_json(
                    {
                        "agent_name": primary_agent_name,
                        "confidence": selected_agent.confidence,
                        "is_followup": selected_agent.is_followup,
                        "is_parallel": should_execute_parallel,
                        "parallel_agents": parallel_agents,
                        "parallel_reason": parallel_reason,
                        "source_agents": agent_names,
                    }
                )
                try:
                    with (
                        jt.tracer.start_as_current_span("stream-response")
                        if jt.telemetry_enabled()
                        else nullcontext()
                    ):
                        response = ""
                        final_response = ""
                        agent_name_for_log = primary_agent_name
                        
                        # Execute agents: parallel with synthesis or single with streaming
                        if should_execute_parallel and len(agents_to_invoke) > 1:
                            # PARALLEL MODE: Execute agents with synthesis
                            logger.info(f"Parallel execution with synthesis: {len(agents_to_invoke)} agents")
                            
                            # Use orchestration service for parallel execution + synthesis
                            aggregated = await orchestration_service.orchestrate_parallel_with_synthesis(
                                agents_to_invoke,
                                conv,
                                message,
                                authorization,
                                None  # no image_data in websocket
                            )
                            
                            if aggregated.success:
                                response = aggregated.synthesized_response
                                final_response = aggregated.synthesized_response
                                # Send source agent names before the synthesized response
                                source_agents_str = ", ".join(aggregated.source_agents)
                                await websocket.send_json({
                                    "event": "parallel_synthesis_complete",
                                    "source_agents": source_agents_str
                                })
                                # Stream the synthesized response
                                await websocket.send_text(final_response)
                                logger.info("------------FOR PARALLEL AGENT------------")
                                for agent_name in aggregated.source_agents:
                                    logger.info(".....for agent name calling celery.."+str(agent_name))
                                    app.send_task("content_update.tasks.update_metadata", 
                                                args=[agent_name,final_response])                                                                        
                            else:
                                error_msg = f"Parallel execution failed: {aggregated.error}"
                                await websocket.send_text(error_msg)
                                response = error_msg
                        else:
                            # SINGLE AGENT MODE: Stream response from primary agent
                            logger.info(f"Single agent streaming: {primary_agent_name}")
                            chunks = []
                            async for content in agents_to_invoke[0].invoke_stream(conv, authorization=authorization):
                                try:
                                    extra_data: ExtraData = ExtraData.new_from_json(content)
                                    context_directives = parse_context_directives(extra_data)
                                    await conv_manager.process_context_directives(conv, context_directives)
                                except Exception:
                                    chunks.append(content)
                                    response = f"{response}{content}"
                                    await websocket.send_text(content)
                            final_response = "".join(chunks)
                    with (
                        jt.tracer.start_as_current_span("update-history-assistant")
                        if jt.telemetry_enabled()
                        else nullcontext()
                    ):
                        agent_response_log = (
                        f"\n========== AGENT RESPONSE ==========\n"
                        f"Agent Name : {primary_agent_name}\n"
                        f"Parallel   : {should_execute_parallel}\n"
                        f"-----------------------------------\n"
                        f"{final_response}\n"
                        f"===================================\n")
                        # TF-IDF keyword extraction
                        logger.info("------------FOR SINGLE AGENT TF IDF extraction------------")
                        #if chroma_client:
                        #    try:
                        #        collection = chroma_client.get_collection()
                        #        logger.info(".....COLLECTION...."+str(collection))
            
                        #        agent_info = tfidf_service.get_agent_details(collection, primary_agent_name)
                        #    except Exception as e:
                        #        logger.error("agent detail failed......"+str(e))
                        #    if agent_info:
                        #        try:
                        #            new_keywords = tfidf_service.learn_keywords(agent_info, primary_agent_name, final_response)
                                    
                        #            logger.info(f"TFIDF | agent={primary_agent_name} | learned_keywords={new_keywords}")
                        app.send_task("content_update.tasks.update_metadata", 
                        args=[primary_agent_name,final_response])
                                
                    #  THIS IS THE LINE YOU ASKED ABOUT
                        logger.info(agent_response_log)
                        # Add response to conversation history
                        await conv_manager.add_agent_message(conv, final_response, primary_agent_name)
                except Exception as e:
                    agent_list = ", ".join([a.name for a in agents_to_invoke])
                    resp = f"There is something wrong with {agent_list}. Please try with a different query."
                    await websocket.send_text(resp)
                    logger.info(resp)
                    logger.info(str(e))
    except WebSocketDisconnect:
        conn_manager.disconnect(websocket)
