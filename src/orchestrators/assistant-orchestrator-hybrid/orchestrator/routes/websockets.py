
import logging
import time
import os

from contextlib import nullcontext
from concurrent.futures import ThreadPoolExecutor

from fastapi import (
    APIRouter,
    WebSocket,
    WebSocketDisconnect,
)
from ska_utils import get_telemetry

from context_directive import parse_context_directives
from jose_types import ExtraData

logger = logging.getLogger(__name__)

# Load parallel processing configuration from environment
ENABLE_PARALLEL_PROCESSING = os.getenv("TA_ENABLE_PARALLEL_PROCESSING", "false").lower() == "true"
PARALLEL_MAX_AGENTS = int(os.getenv("TA_PARALLEL_MAX_AGENTS", "2"))

# Log parallel processing configuration at startup
logger.info(f"WebSocket Parallel Processing: {'ENABLED' if ENABLE_PARALLEL_PROCESSING else 'DISABLED'}")
if ENABLE_PARALLEL_PROCESSING:
    logger.info(f"   Max parallel agents: {PARALLEL_MAX_AGENTS}")

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


def _execute_agent_sync(agent, conv, authorization, image_data=None):
    """Execute agent synchronously for parallel execution."""
    try:
        agent_start = time.time()
        logger.info(f"Starting: {agent.name}")
        
        response = agent.invoke_api(conv, authorization, image_data)
        agent_response = response.get("output_raw", "No output available.")
        
        agent_duration = time.time() - agent_start
        logger.info(f"Completed: {agent.name} ({agent_duration:.2f}s)")
        
        return {
            "success": True,
            "agent_name": agent.name,
            "response": agent_response,
            "raw_response": response,
            "duration": agent_duration
        }
    except Exception as e:
        agent_duration = time.time() - agent_start
        logger.error(f"Failed: {agent.name} ({agent_duration:.2f}s): {e}")
        return {
            "success": False,
            "agent_name": agent.name,
            "error": str(e),
            "duration": agent_duration
        }


async def _execute_parallel_agents_ws(agents, conv, authorization):
    """Execute multiple agents in parallel using ThreadPoolExecutor."""
    try:
        logger.info(f"ARALLEL EXECUTION - Starting {len(agents)} agents...")
        parallel_start = time.time()
        
        results = {}
        with ThreadPoolExecutor(max_workers=min(len(agents), 5), thread_name_prefix="agent-") as executor:
            futures = {
                executor.submit(_execute_agent_sync, agent, conv, authorization, None): agent.name
                for agent in agents
            }
            
            for future in futures:
                agent_name = futures[future]
                try:
                    result = future.result(timeout=60)
                    results[agent_name] = result
                except Exception as e:
                    logger.error(f"ThreadPoolExecutor timeout/error for {agent_name}: {e}")
                    results[agent_name] = {
                        "success": False,
                        "agent_name": agent_name,
                        "error": f"Timeout or execution error: {str(e)}"
                    }
        
        parallel_duration = time.time() - parallel_start
        
        successful = sum(1 for r in results.values() if r.get("success"))
        failed = len(results) - successful
        
        logger.info(f"PARALLEL EXECUTION COMPLETE")
        logger.info(f"Successful: {successful} agents")
        logger.info(f"Failed: {failed} agents")
        logger.info(f"Total duration: {parallel_duration:.2f}s")
        
        return {
            "success": True,
            "parallel_mode": True,
            "results": results,
            "duration": parallel_duration,
            "total_agents": len(agents),
            "successful_agents": successful,
            "failed_agents": failed
        }
    except Exception as e:
        logger.error(f"Parallel execution failed: {e}", exc_info=True)
        return {
            "success": False,
            "parallel_mode": True,
            "error": str(e)
        }


async def _stream_responses_sequentially(agents, conv, authorization, websocket):
    """Stream agent responses sequentially without aggregation."""
    try:
        logger.info(f"SEQUENTIAL STREAMING - {len(agents)} agents")
        
        all_responses = {}
        for idx, agent in enumerate(agents, 1):
            logger.info(f"[{idx}/{len(agents)}] Starting: {agent.name}")
            
            try:
                response_content = ""
                
                # Send separator header for each agent
                agent_header = f"\n{'='*60}\n[Agent {idx}/{len(agents)}] {agent.name}\n{'='*60}\n"
                await websocket.send_text(agent_header)
                logger.info(f"   Streaming response from {agent.name}...")
                
                # Stream response from agent
                async for content in agent.invoke_stream(conv, authorization=authorization):
                    try:
                        extra_data: ExtraData = ExtraData.new_from_json(content)
                        context_directives = parse_context_directives(extra_data)
                        await conv_manager.process_context_directives(conv, context_directives)
                    except Exception:
                        response_content = f"{response_content}{content}"
                        await websocket.send_text(content)
                
                all_responses[agent.name] = response_content
                logger.info(f"Completed: {agent.name}")
                
            except Exception as e:
                logger.error(f"Failed: {agent.name}: {e}")
                error_msg = f"Error from {agent.name}: {str(e)}\n"
                all_responses[agent.name] = error_msg
                await websocket.send_text(error_msg)
        
        logger.info(f"SEQUENTIAL STREAMING COMPLETE")
        return all_responses
        
    except Exception as e:
        logger.error(f"Sequential streaming failed: {e}", exc_info=True)
        return {}


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
                    selected_agent = await rec_chooser.choose_recipient(message, conv)
                    
                    # Use primary_agent, fallback to agent_name for backward compatibility
                    primary_agent_name = selected_agent.primary_agent or selected_agent.agent_name
                    secondary_agent_name = selected_agent.secondary_agent
                    
                    if primary_agent_name not in agent_catalog.agents:
                        primary_agent = fallback_agent
                        sel_agent_name = fallback_agent.name
                    else:
                        primary_agent = agent_catalog.agents[primary_agent_name]
                        sel_agent_name = primary_agent.name
                    
                    # Get secondary agent if available
                    secondary_agent = None
                    if secondary_agent_name and secondary_agent_name in agent_catalog.agents:
                        secondary_agent = agent_catalog.agents[secondary_agent_name]
                        logger.info(f"Secondary agent loaded: {secondary_agent.name}")
                    elif secondary_agent_name:
                        logger.warning(f"Secondary agent '{secondary_agent_name}' not found in catalog")
                    
                    # Determine if parallel execution should happen
                    should_execute_parallel = (
                        ENABLE_PARALLEL_PROCESSING and 
                        secondary_agent is not None
                    )
                    
                    # Set parallel flags for response
                    parallel_agents = [secondary_agent.name] if secondary_agent else []
                    parallel_reason = selected_agent.confidence if secondary_agent else ""

                with (
                    jt.tracer.start_as_current_span("update-history-user")
                    if jt.telemetry_enabled()
                    else nullcontext()
                ):
                    # Add the current message to conversation history
                    await conv_manager.add_user_message(conv, message, sel_agent_name)

                # Log the agent selection decision
                logger.info("=" * 80)
                logger.info("AGENT SELECTION DECISION:")
                logger.info(f"User Message: {message}")
                logger.info(f"Primary Agent: {sel_agent_name}")
                logger.info(f"Confidence: {selected_agent.confidence}")
                logger.info(f"Is Follow-up: {selected_agent.is_followup}")
                if secondary_agent:
                    logger.info(f"SECONDARY AGENT (Parallel): {secondary_agent.name}")
                logger.info("=" * 80)

                # Notify the client of which agent(s) will be handling this message
                await websocket.send_json(
                    {
                        "agent_name": sel_agent_name,
                        "confidence": selected_agent.confidence,
                        "is_followup": selected_agent.is_followup,
                        "is_parallel": should_execute_parallel,
                        "parallel_agents": parallel_agents,
                        "parallel_reason": parallel_reason,
                    }
                )
                try:
                    with (
                        jt.tracer.start_as_current_span("stream-response")
                        if jt.telemetry_enabled()
                        else nullcontext()
                    ):
                        response = ""
                        
                        # Execute agents: primary only or primary + secondary (parallel)
                        if should_execute_parallel and secondary_agent:
                            # PARALLEL MODE: Execute both agents sequentially (no true parallelism, sequential streaming)
                            logger.info(f"EXECUTING BOTH AGENTS (Sequential Streaming)")
                            logger.info(f"1. Primary: {sel_agent_name}")
                            logger.info(f"2. Secondary: {secondary_agent.name}")
                            
                            agents_to_execute = [primary_agent, secondary_agent]
                            
                            await _stream_responses_sequentially(
                                agents_to_execute,
                                conv,
                                authorization,
                                websocket
                            )
                        else:
                            # SINGLE AGENT MODE: Execute primary agent only
                            logger.info(f"EXECUTING PRIMARY AGENT ONLY: {sel_agent_name}")
                            
                            async for content in primary_agent.invoke_stream(conv, authorization=authorization):
                                try:
                                    extra_data: ExtraData = ExtraData.new_from_json(content)
                                    context_directives = parse_context_directives(extra_data)
                                    await conv_manager.process_context_directives(conv, context_directives)
                                except Exception:
                                    response = f"{response}{content}"
                                    await websocket.send_text(content)

                    with (
                        jt.tracer.start_as_current_span("update-history-assistant")
                        if jt.telemetry_enabled()
                        else nullcontext()
                    ):
                        # Add response to conversation history
                        await conv_manager.add_agent_message(conv, response, sel_agent_name)
                except Exception as e:
                    resp = f"There is something wrong with the {sel_agent_name}{f' & {secondary_agent.name}' if secondary_agent else ''}. Please try with a different query."
                    await websocket.send_text(resp)
                    logger.info(resp)
                    logger.info(str(e))
    except WebSocketDisconnect:
        conn_manager.disconnect(websocket)
