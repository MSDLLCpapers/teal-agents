import logging
import time

from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from context_directive import parse_context_directives
from jose_types import ExtraData
from model.requests import ConversationMessageRequest
from typing import Dict, Any, List

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

logger = logging.getLogger(__name__)

conv_manager = get_conv_manager()
conn_manager = get_conn_manager()
rec_chooser = get_rec_chooser()
config = get_config()
agent_catalog = get_agent_catalog()
fallback_agent = get_fallback_agent()
cache_user_context = get_user_context_cache()

router = APIRouter()
header_scheme = APIKeyHeader(name="authorization", auto_error=False)

def _execute_agent_sync(agent, conv, authorization, image_data=None) -> Dict[str, Any]:
    """Execute agent synchronously (for use in ThreadPoolExecutor)."""
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


async def _execute_parallel_agents(agents: List, conv, authorization, image_data=None) -> Dict[str, Any]:
    """Execute multiple agents in parallel using ThreadPoolExecutor."""
    try:
        logger.info(f"PARALLEL EXECUTION - Starting {len(agents)} agents...")
        parallel_start = time.time()
        
        results = {}
        with ThreadPoolExecutor(max_workers=min(len(agents), 5), thread_name_prefix="agent-") as executor:
            futures = {
                executor.submit(_execute_agent_sync, agent, conv, authorization, image_data): agent.name
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


async def _aggregate_parallel_responses(parallel_results: Dict[str, Any], message: str = None) -> str:
    """Aggregate multiple agent responses using LLM synthesis."""
    try:
        logger.info("AGGREGATING PARALLEL RESPONSES")
        
        responses_text = ""
        successful_agents = 0
        failed_agents = 0
        
        for agent_name, result in parallel_results.get("results", {}).items():
            if result.get("success"):
                response_text = result.get("response", "No response")
                responses_text += f"\n## {agent_name}\n{response_text}\n"
                successful_agents += 1
                logger.info(f"{agent_name}: {len(response_text)} chars")
            else:
                error_msg = result.get("error", "Unknown error")
                responses_text += f"\n## {agent_name} (FAILED)\n Error: {error_msg}\n"
                failed_agents += 1
                logger.warning(f"Error: {agent_name}: {error_msg}")
        
        logger.info(f"   Total: {successful_agents} successful, {failed_agents} failed")
        
        if successful_agents == 0:
            logger.warning("All parallel agents failed - returning error summary")
            return responses_text
        
        logger.info(f"   Invoking LLM to synthesize {successful_agents} agent responses...")
        
        try:
            from openai import AzureOpenAI
            
            synthesis_prompt = f"""You are an expert at synthesizing information from multiple specialized agents.

User Query: "{message if message else 'Unknown query'}"

Responses from different agents:
{responses_text}

Your task:
1. Synthesize all responses into a cohesive, comprehensive answer
2. For each agent's contribution, clearly label it with the agent name
3. Highlight any contradictions or complementary information
4. Organize information logically by topic and theme, not just by agent
5. Remove redundancy while preserving unique insights
6. Create a unified narrative that flows well

Format:
- Start with a brief summary of the key findings
- Then organize by topic with agent attributions in brackets like [AgentName]
- End with any important notes or caveats

Make the response professional, coherent, and directly address the user's query."""

            client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version="2024-02-01",
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            
            logger.info("Sending synthesis request to LLM...")
            synthesis_start = time.time()
            
            response = client.chat.completions.create(
                model=os.getenv("AZURE_OPENAI_CHAT_MODEL", "gpt-4o-2024-11-20"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at synthesizing information from multiple specialized agents and creating unified, coherent responses."
                    },
                    {
                        "role": "user",
                        "content": synthesis_prompt
                    }
                ],
                temperature=0.3,
                max_tokens=2000
            )
            
            synthesis_duration = time.time() - synthesis_start
            aggregated_response = response.choices[0].message.content.strip()
            
            logger.info(f"AGGREGATION COMPLETE")
            logger.info(f"   LLM synthesis took {synthesis_duration:.2f}s")
            logger.info(f"   Output length: {len(aggregated_response)} chars")
            
            return aggregated_response
            
        except Exception as llm_error:
            logger.error(f"LLM synthesis failed: {llm_error}", exc_info=True)
            logger.info("Falling back to simple concatenation...")
            
            fallback_response = "**Parallel Agent Responses:**\n"
            for agent_name, result in parallel_results.get("results", {}).items():
                if result.get("success"):
                    fallback_response += f"\n## {agent_name}\n{result.get('response', 'No response')}\n"
                else:
                    fallback_response += f"\n## {agent_name} (Failed)\nError: {result.get('error', 'Unknown error')}\n"
            
            return fallback_response
            
    except Exception as e:
        logger.error(f"Response aggregation failed: {e}", exc_info=True)
        return f"Error aggregating responses: {e}"


async def _execute_single_agent(agent, conv, authorization, image_data=None) -> Dict[str, Any]:
    """Execute a single agent and return its response. [DEPRECATED - use inline execution]"""
    try:
        response = agent.invoke_api(conv, authorization, image_data)
        agent_response = response.get("output_raw", "No output available.")
        
        # Process extra data if present
        extra_data = response.get("extra_data")
        if extra_data is not None:
            extra_data_instance = ExtraData.new_from_json(extra_data)
            context_directives = parse_context_directives(extra_data_instance)
            await conv_manager.process_context_directives(conv, context_directives)
        
        return {
            "success": True,
            "agent_name": agent.name,
            "response": agent_response,
            "raw_response": response
        }
    except Exception as e:
        logger.error(f"Error executing agent {agent.name}: {e}")
        return {
            "success": False,
            "agent_name": agent.name,
            "error": str(e)
        }


@router.get(
    "/conversations/{conversation_id}/messages",
    tags=["Conversations"],
    description="Get the full conversation history based on a session id.",
)
async def get_conversation_by_id(user_id: str, conversation_id: str):
    try:
        logger.info(f"Fetching conversation {conversation_id} for user {user_id}")
        conv = await conv_manager.get_conversation(user_id, conversation_id)
        logger.info(f"Conversation retrieved successfully")
        return {"conversation": conv}
    except Exception as e:
        logger.error(f"Failed to get conversation: {e}", exc_info=True)
        raise HTTPException(
            status_code=404,
            detail=f"Unable to get conversation with conversation_id: {conversation_id} --- {e}",
        ) from e


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
        try:
            in_memory_user_context = cache_user_context.get_user_context_from_cache(
                user_id=user_id
            ).model_dump()["user_context"]
            await conv_manager.add_transient_context(conv, in_memory_user_context)
        except Exception as e:
            logger.warning(f"Failed to get user context: {e}")
    
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
            # Select the best agent(s) for this message
            try:
                selected_agent = await rec_chooser.choose_recipient(request.message, conv)
                logger.info(f"Selected from recipient chooser: {selected_agent.agent_name}")
                logger.info(f"Is Parallel: {selected_agent.is_parallel}")
                if selected_agent.is_parallel:
                    logger.info(f"Parallel Agents: {', '.join(selected_agent.parallel_agents)}")
            except Exception as e:
                logger.error(f"Error in recipient chooser: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error retrieving agent to handle conversation message --- {e}",
                ) from e

            # Determine which agents to invoke
            agents_to_invoke = []
            primary_agent_name = selected_agent.agent_name
            
            try:
                # Get primary agent
                if selected_agent.agent_name in agent_catalog.agents:
                    primary_agent = agent_catalog.agents[selected_agent.agent_name]
                    agents_to_invoke.append(primary_agent)
                else:
                    logger.error(f"Primary agent {selected_agent.agent_name} not found in catalog")
                    logger.error(f"Available agents: {list(agent_catalog.agents.keys())}")
                    primary_agent = fallback_agent
                    agents_to_invoke.append(primary_agent)
                    primary_agent_name = fallback_agent.name
                
                # Get parallel agents if needed
                if selected_agent.is_parallel and selected_agent.parallel_agents:
                    logger.info(f"PARALLEL MODE DETECTED - Adding {len(selected_agent.parallel_agents)} parallel agents")
                    logger.info(f"Catalog keys: {list(agent_catalog.agents.keys())}")
                    for parallel_agent_name in selected_agent.parallel_agents:
                        logger.info(f"Looking for: '{parallel_agent_name}' (type: {type(parallel_agent_name).__name__})")
                        if parallel_agent_name in agent_catalog.agents:
                            agents_to_invoke.append(agent_catalog.agents[parallel_agent_name])
                            logger.info(f"Added parallel agent: {parallel_agent_name}")
                        else:
                            logger.warning(f"Parallel agent '{parallel_agent_name}' not found in catalog")
                            logger.warning(f"Trying case-insensitive match...")
                            # Try case-insensitive match
                            found = False
                            for catalog_key in agent_catalog.agents.keys():
                                if catalog_key.lower() == parallel_agent_name.lower():
                                    agents_to_invoke.append(agent_catalog.agents[catalog_key])
                                    logger.info(f"Added parallel agent (case-insensitive): {catalog_key}")
                                    found = True
                                    break
                            if not found:
                                logger.warning(f"Available catalog agents: {list(agent_catalog.agents.keys())}")
                else:
                    logger.info(f"Not parallel mode or no parallel agents. is_parallel={selected_agent.is_parallel}, parallel_agents={selected_agent.parallel_agents}")
                
                logger.info(f"Total agents to invoke: {len(agents_to_invoke)}")
                
            except Exception as e:
                logger.error(f"Error resolving agents: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error resolving agents --- {e}",
                ) from e
            
            with (
                jt.tracer.start_as_current_span("update-history-user")
                if jt.telemetry_enabled()
                else nullcontext()
            ):
                # Add user message to history
                try:
                    await conv_manager.add_user_message(conv, request.message, primary_agent_name)
                except Exception as e:
                    logger.error(f"Error adding user message: {e}", exc_info=True)
                    raise HTTPException(
                        status_code=500,
                        detail=f"Error adding new message to conversation history --- {e}",
                    ) from e
            
            with (
                jt.tracer.start_as_current_span("agent-response")
                if jt.telemetry_enabled()
                else nullcontext()
            ):
                logger.info("Begin processing agent invocation")
                logger.info(f"PARALLEL CHECK: is_parallel={selected_agent.is_parallel}, agents_to_invoke={len(agents_to_invoke)}, parallel_agents_list={selected_agent.parallel_agents}")
                
                # Execute agents (parallel or single)
                if selected_agent.is_parallel and len(agents_to_invoke) > 1:
                    logger.info(f"TRIGGERING PARALLEL EXECUTION - {len(agents_to_invoke)} agents")
                    logger.info(f"EXECUTING {len(agents_to_invoke)} AGENTS IN PARALLEL")
                    logger.info(f"Primary: {selected_agent.agent_name}")
                    logger.info(f"Parallel: {', '.join(selected_agent.parallel_agents)}")
                    if hasattr(selected_agent, 'parallel_reason'):
                        logger.info(f"Reason: {selected_agent.parallel_reason}")
                    
                    parallel_result = await _execute_parallel_agents(
                        agents_to_invoke,
                        conv,
                        authorization,
                        request.image_data
                    )
                    
                    if not parallel_result.get("success"):
                        logger.error(f"Parallel execution failed: {parallel_result.get('error')}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Error executing parallel agents: {parallel_result.get('error', 'Unknown error')}"
                        )
                    
                    agent_response = await _aggregate_parallel_responses(parallel_result, request.message)
                else:
                    # Single agent execution
                    logger.info(f"EXECUTING SINGLE AGENT: {agents_to_invoke[0].name}")
                    agent_start = time.time()
                    
                    try:
                        response = agents_to_invoke[0].invoke_api(conv, authorization, request.image_data)
                        agent_response = response.get("output_raw", "No output available.")
                        
                        # Process extra data if present
                        extra_data = response.get("extra_data")
                        if extra_data is not None:
                            try:
                                extra_data_instance = ExtraData.new_from_json(extra_data)
                                context_directives = parse_context_directives(extra_data_instance)
                                await conv_manager.process_context_directives(conv, context_directives)
                            except Exception as e:
                                logger.warning(f"Failed to process extra data: {e}")
                        
                        agent_duration = time.time() - agent_start
                        logger.info(f"Agent execution completed in {agent_duration:.2f}s")
                        
                    except Exception as e:
                        logger.error(f"Agent execution failed: {e}", exc_info=True)
                        raise HTTPException(
                            status_code=500,
                            detail=f"Error executing agent: {str(e)}"
                        )
        
        with (
            jt.tracer.start_as_current_span("update-history-assistant")
            if jt.telemetry_enabled()
            else nullcontext()
        ):
            # Add response to conversation history
            try:
                await conv_manager.add_agent_message(conv, agent_response, primary_agent_name)
            except Exception as e:
                logger.error(f"Error adding agent message: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error adding response to conversation history --- {e}",
                ) from e
        
        try:
            conversation_result = await conv_manager.get_last_response(conv)
        except Exception as e:
            logger.error(f"Error getting conversation result: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail=f"Error retrieving conversation result --- {e}",
            ) from e
    
    return {"conversation": conversation_result}


@router.post(
    "/conversations",
    tags=["Conversations"],
    description="Start a new conversation. Returns new session ID and agent response.",
)
async def new_conversation(user_id: str):
    jt = get_telemetry()
    try:
        logger.info(f"Creating new conversation for user {user_id}")
        with (
            jt.tracer.start_as_current_span("init-conversation")
            if jt.telemetry_enabled()
            else nullcontext()
        ):
            try:
                conv = await conv_manager.new_conversation(user_id, False)
                logger.info(f"New conversation created: {conv.conversation_id}")
                return {"conversation_id": conv.conversation_id, "user_id": conv.user_id}
            except Exception as e:
                logger.error(f"Failed to create conversation: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500, detail=f"Error creating new conversation --- {e}"
                ) from e
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in new_conversation: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Unexpected error creating conversation --- {e}"
        ) from e


@router.get(
    "/healthcheck",
    tags=["Health"],
    description="Check the health status of Assistant Orchestrator.",
)
async def healthcheck():
    return {"status": "healthy"}
