"""
Customized API Router for Assistant Orchestrator

This router extends the default Assistant Orchestrator router to handle
agent selection and execution.

Architecture:
- recipient_chooser.py: SELECTS the best agent for user queries
- apis.py (this file): EXECUTES the selected agent via AgentOrchestrationService
- Router handles HTTP request/response, delegates to service layer
"""

import logging
from contextlib import nullcontext
from context_directive import parse_context_directives
from jose_types import ExtraData
from model.requests import ConversationMessageRequest, AgentRegistrationRequest

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import APIKeyHeader
from ska_utils import get_telemetry, AppConfig

from .deps import (
    get_agent_catalog,
    get_config,
    get_conn_manager,
    get_conv_manager,
    get_fallback_agent,
    get_rec_chooser,
    get_user_context_cache,
    get_orchestration_service,
    get_agent_registry_manager,
)

logger = logging.getLogger(__name__)

conv_manager = get_conv_manager()
conn_manager = get_conn_manager()
rec_chooser = get_rec_chooser()
config = get_config()
agent_catalog = get_agent_catalog()
fallback_agent = get_fallback_agent()
cache_user_context = get_user_context_cache()

# Get orchestration service from deps
orchestration_service = get_orchestration_service()

router = APIRouter()
header_scheme = APIKeyHeader(name="authorization", auto_error=False)


@router.get(
    "/conversations/{conversation_id}/messages",
    tags=["Conversations"],
    description="Get the full conversation history based on a session id.",
)
async def get_conversation_by_id(user_id: str, conversation_id: str):
    try:
        logger.debug(f"Fetching conversation {conversation_id} for user {user_id}")
        conv = await conv_manager.get_conversation(user_id, conversation_id)
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
                selected_agent = await rec_chooser.choose_recipient(request.message, conv, authorization)
                logger.info(f"Agent selected: {selected_agent.agent_name} (parallel={selected_agent.is_parallel})")
                if selected_agent.is_parallel:
                    logger.debug(f"Parallel agents: {', '.join(selected_agent.parallel_agents)}")
            except Exception as e:
                logger.error(f"Error in recipient chooser: {e}", exc_info=True)
                raise HTTPException(
                    status_code=500,
                    detail=f"Error retrieving agent to handle conversation message --- {e}",
                ) from e

            # Resolve agents using recipient chooser
            try:
                agents_to_invoke, primary_agent_name = rec_chooser.resolve_agents(
                    selected_agent, agent_catalog, fallback_agent
                )
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
                # Execute agents (parallel or single)
                # Initialize source_agents_str for tracking which agents contributed
                source_agents_str = ""
                
                if selected_agent.is_parallel and len(agents_to_invoke) > 1:
                    logger.info(f"Parallel execution: {len(agents_to_invoke)} agents")
                    logger.debug(f"Primary: {selected_agent.agent_name}")
                    logger.debug(f"Parallel: {', '.join(selected_agent.parallel_agents)}")
                    
                    # Use orchestration service for parallel execution + synthesis
                    aggregated = await orchestration_service.orchestrate_parallel_with_synthesis(
                        agents_to_invoke,
                        conv,
                        request.message,
                        authorization,
                        request.image_data
                    )
                    
                    if not aggregated.success:
                        logger.error(f"Parallel execution failed: {aggregated.error}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Error executing parallel agents: {aggregated.error or 'Unknown error'}"
                        )
                    
                    agent_response = aggregated.synthesized_response
                    # Include source agent names in primary_agent_name for parallel responses
                    source_agents_str = ", ".join(aggregated.source_agents)
                    primary_agent_name = source_agents_str
                    logger.info(f"Parallel response synthesized from agents: {source_agents_str}")
                else:
                    # Single agent execution using orchestration service
                    logger.info(f"Single agent execution: {agents_to_invoke[0].name}")
                    
                    # Set source_agents_str for single agent
                    source_agents_str = agents_to_invoke[0].name
                    
                    result = orchestration_service.execute_single_agent(
                        agents_to_invoke[0],
                        conv,
                        authorization,
                        request.image_data
                    )
                    
                    if not result.success:
                        logger.error(f"Agent execution failed: {result.error}")
                        raise HTTPException(
                            status_code=500,
                            detail=f"Error executing agent: {result.error}"
                        )
                    
                    agent_response = result.response
                    
                    # Process extra data if present
                    if result.raw_response:
                        extra_data = result.raw_response.get("extra_data")
                        if extra_data is not None:
                            try:
                                extra_data_instance = ExtraData.new_from_json(extra_data)
                                context_directives = parse_context_directives(extra_data_instance)
                                await conv_manager.process_context_directives(conv, context_directives)
                            except Exception as e:
                                logger.warning(f"Failed to process extra data: {e}")
        
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
    
    return {"conversation": conversation_result, "source_agents": source_agents_str}


@router.post(
    "/conversations",
    tags=["Conversations"],
    description="Start a new conversation. Returns new session ID and agent response.",
)
async def new_conversation(user_id: str):
    jt = get_telemetry()
    try:
        logger.debug(f"Creating new conversation for user {user_id}")
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


@router.post(
    "/agents/sync",
    tags=["Agents"],
    description="Add, update, or sync agents in the agents-registry.",
)
async def register_agent(
    request: AgentRegistrationRequest,
    authorization: str = Depends(header_scheme),
):
    """
    Add or update an agent in the agents-registry.
    
    The endpoint validates the token from Authorization header, then:
    - For 'new': Creates a new agent entry
    - For 'update': Updates an existing agent entry
    
    Additionally, any agents in the database not in the provided 'agents' list
    will be soft deleted (sync behavior).
    """
    app_config = AppConfig()
    expected_token = app_config.get("AGENT_REGISTRATION_TOKEN")
    if not expected_token or authorization != expected_token:
        raise HTTPException(status_code=401, detail="Invalid or missing registration token")
    
    agent_registry_manager = get_agent_registry_manager()
    
    try:
        result = await agent_registry_manager.sync_agents(
            agent_names=request.agents,
            agent_name=request.service_name,
            description=request.description,
            desc_keywords=request.desc_keywords,
            deployment_name=request.deployment_name
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        logger.error(f"Error in register_agent: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error registering agent: {e}") from e
