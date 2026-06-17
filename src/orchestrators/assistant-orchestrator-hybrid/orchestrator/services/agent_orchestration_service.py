"""
Agent Orchestration Service.

This service provides unified orchestration for:
- Single agent execution
- Parallel agent execution
- Response synthesis/aggregation from multiple agents
- Sequential streaming for WebSocket connections

Architecture:
- Execution logic separated from route handlers
- OpenAI client integration for response synthesis
- Consistent result models across sync and async operations
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional, Dict, Any

from context_directive import parse_context_directives
from jose_types import ExtraData

from integration.openai_client import AzureOpenAIClient
from model.agent_execution import (
    AgentExecutionResult,
    ParallelExecutionResult,
    AggregatedResponse
)
from prompts.reranking import (
    build_response_synthesis_prompt,
    format_parallel_responses,
    RESPONSE_SYNTHESIS_SYSTEM_PROMPT
)

logger = logging.getLogger(__name__)


class AgentOrchestrationService:
    """
    Unified service for agent execution and response synthesis.
    
    This service encapsulates all business logic for:
    1. Executing single agents
    2. Executing multiple agents in parallel
    3. Synthesizing responses from multiple agents using LLM
    4. Streaming responses sequentially over WebSocket
    """
    
    def __init__(
        self,
        openai_client: AzureOpenAIClient,
        max_parallel_workers: int = 5,
        execution_timeout: int = 60
    ):
        """
        Initialize the orchestration service.
        
        Args:
            openai_client: Azure OpenAI client for response synthesis
            max_parallel_workers: Maximum concurrent agent executions
            execution_timeout: Timeout in seconds for individual agent execution
        """
        self.openai_client = openai_client
        self.max_parallel_workers = max_parallel_workers
        self.execution_timeout = execution_timeout
        logger.info(f"AgentOrchestrationService initialized")
        logger.debug(f"Max parallel workers: {max_parallel_workers}")
        logger.debug(f"Execution timeout: {execution_timeout}s")
    
    # =========================================================================
    # Single Agent Execution
    # =========================================================================
    
    def execute_single_agent(
        self,
        agent,
        conv,
        authorization: Optional[str] = None,
        image_data: Optional[str] = None
    ) -> AgentExecutionResult:
        """
        Execute a single agent synchronously.
        
        Args:
            agent: Agent instance to execute
            conv: Conversation context
            authorization: Authorization header/token
            image_data: Optional image data for multimodal agents
            
        Returns:
            AgentExecutionResult with response or error
        """
        try:
            logger.debug(f"Executing agent: {agent.name}")
            
            response = agent.invoke_api(conv, authorization, image_data)
            agent_response = response.get("output_raw", "No output available.")
            
            logger.debug(f"Agent {agent.name} completed successfully")
            
            return AgentExecutionResult(
                success=True,
                agent_name=agent.name,
                response=agent_response,
                raw_response=response,
                duration=0.0  # Duration removed as per refactor plan
            )
        except Exception as e:
            logger.error(f"Agent {agent.name} failed: {e}", exc_info=True)
            return AgentExecutionResult(
                success=False,
                agent_name=agent.name,
                response="",
                error=str(e),
                duration=0.0
            )
    
    # =========================================================================
    # Parallel Agent Execution
    # =========================================================================
    
    async def execute_parallel_agents(
        self,
        agents: List,
        conv,
        authorization: Optional[str] = None,
        image_data: Optional[str] = None
    ) -> ParallelExecutionResult:
        """
        Execute multiple agents in parallel using asyncio.run_in_executor.
        
        This properly integrates ThreadPoolExecutor with the asyncio event loop,
        allowing the loop to remain responsive while agents execute in threads.
        
        Args:
            agents: List of agent instances to execute
            conv: Conversation context
            authorization: Authorization header/token
            image_data: Optional image data
            
        Returns:
            ParallelExecutionResult with all agent results
        """
        try:
            logger.info(f"Starting parallel execution of {len(agents)} agents")
            
            # Get the current event loop
            loop = asyncio.get_running_loop()
            
            # Create thread pool executor
            max_workers = min(len(agents), self.max_parallel_workers)
            executor = ThreadPoolExecutor(
                max_workers=max_workers,
                thread_name_prefix="agent-exec-"
            )
            
            try:
                # Create async tasks that run sync functions in executor
                tasks = [
                    loop.run_in_executor(
                        executor,
                        self.execute_single_agent,
                        agent,
                        conv,
                        authorization,
                        image_data
                    )
                    for agent in agents
                ]
                
                # Wait for all tasks with timeout, capturing exceptions
                results_list = await asyncio.wait_for(
                    asyncio.gather(*tasks, return_exceptions=True),
                    timeout=self.execution_timeout
                )
                
                # Map results to agent names
                results = {}
                for agent, result in zip(agents, results_list):
                    if isinstance(result, Exception):
                        logger.error(f"Parallel execution error for {agent.name}: {result}")
                        results[agent.name] = AgentExecutionResult(
                            success=False,
                            agent_name=agent.name,
                            response="",
                            error=f"Execution error: {str(result)}",
                            duration=0.0
                        )
                    else:
                        results[agent.name] = result
                
                # Calculate statistics
                successful = sum(1 for r in results.values() if r.success)
                failed = len(results) - successful
                
                logger.info(f"Parallel execution complete: {successful} succeeded, {failed} failed")
                
                return ParallelExecutionResult(
                    success=True,
                    parallel_mode=True,
                    results=results,
                    duration=0.0,  # Duration removed as per refactor plan
                    total_agents=len(agents),
                    successful_agents=successful,
                    failed_agents=failed
                )
                
            finally:
                # Ensure executor is properly shut down
                executor.shutdown(wait=False)
                
        except asyncio.TimeoutError:
            logger.error(f"Parallel execution timed out after {self.execution_timeout}s")
            return ParallelExecutionResult(
                success=False,
                parallel_mode=True,
                results={},
                duration=0.0,
                total_agents=len(agents),
                successful_agents=0,
                failed_agents=len(agents),
                error=f"Execution timed out after {self.execution_timeout}s"
            )
        except Exception as e:
            logger.error(f"Parallel execution failed: {e}", exc_info=True)
            return ParallelExecutionResult(
                success=False,
                parallel_mode=True,
                results={},
                duration=0.0,
                total_agents=len(agents),
                successful_agents=0,
                failed_agents=len(agents),
                error=str(e)
            )
    
    # =========================================================================
    # Response Synthesis
    # =========================================================================
    
    async def synthesize_responses(
        self,
        parallel_result: ParallelExecutionResult,
        user_query: str
    ) -> AggregatedResponse:
        """
        Synthesize multiple agent responses into a unified response using LLM.
        
        Args:
            parallel_result: Result from parallel agent execution
            user_query: Original user query for context
            
        Returns:
            AggregatedResponse with synthesized content
        """
        try:
            logger.info("Starting response synthesis")
            
            # Format responses for synthesis
            formatted_responses = format_parallel_responses(
                {name: {"success": r.success, "response": r.response, "error": r.error}
                 for name, r in parallel_result.results.items()}
            )
            
            successful = parallel_result.successful_agents
            failed = parallel_result.failed_agents
            
            logger.debug(f"Synthesizing {successful} successful responses")
            
            # Check if we have any successful responses
            if successful == 0:
                logger.warning("No successful responses to synthesize")
                return AggregatedResponse(
                    success=False,
                    synthesized_response=formatted_responses,
                    source_agents=list(parallel_result.results.keys()),
                    successful_count=0,
                    failed_count=failed,
                    synthesis_duration=0.0,
                    total_duration=0.0,
                    fallback_used=True,
                    error="All agents failed"
                )
            
            # Build synthesis prompt
            synthesis_prompt = build_response_synthesis_prompt(
                responses_text=formatted_responses,
                user_message=user_query
            )
            
            try:
                # Call LLM for synthesis
                logger.debug("Invoking LLM for response synthesis")
                
                synthesized_content = self.openai_client.chat_completion(
                    messages=[
                        {
                            "role": "system",
                            "content": RESPONSE_SYNTHESIS_SYSTEM_PROMPT
                        },
                        {
                            "role": "user",
                            "content": synthesis_prompt
                        }
                    ],
                    temperature=0.3,
                    max_tokens=2000
                )
                
                logger.info("Response synthesis completed successfully")
                
                return AggregatedResponse(
                    success=True,
                    synthesized_response=synthesized_content,
                    source_agents=list(parallel_result.results.keys()),
                    successful_count=successful,
                    failed_count=failed,
                    synthesis_duration=0.0,
                    total_duration=0.0,
                    fallback_used=False
                )
                
            except Exception as llm_error:
                logger.error(f"LLM synthesis failed: {llm_error}", exc_info=True)
                logger.info("Falling back to simple response concatenation")
                
                # Fallback: use formatted responses directly
                return AggregatedResponse(
                    success=True,
                    synthesized_response=f"**Multiple Agent Responses:**\n{formatted_responses}",
                    source_agents=list(parallel_result.results.keys()),
                    successful_count=successful,
                    failed_count=failed,
                    synthesis_duration=0.0,
                    total_duration=0.0,
                    fallback_used=True
                )
                
        except Exception as e:
            logger.error(f"Response synthesis failed: {e}", exc_info=True)
            return AggregatedResponse(
                success=False,
                synthesized_response=f"Error synthesizing responses: {str(e)}",
                source_agents=[],
                successful_count=0,
                failed_count=0,
                synthesis_duration=0.0,
                total_duration=0.0,
                fallback_used=True,
                error=str(e)
            )
    
    # =========================================================================
    # Combined Orchestration (Parallel + Synthesis)
    # =========================================================================
    
    async def orchestrate_parallel_with_synthesis(
        self,
        agents: List,
        conv,
        user_query: str,
        authorization: Optional[str] = None,
        image_data: Optional[str] = None
    ) -> AggregatedResponse:
        """
        Execute multiple agents in parallel and synthesize their responses.
        
        This is a convenience method that combines parallel execution
        and response synthesis in a single call.
        
        Args:
            agents: List of agent instances
            conv: Conversation context
            user_query: Original user query
            authorization: Authorization header/token
            image_data: Optional image data
            
        Returns:
            AggregatedResponse with synthesized content
        """
        logger.info(f"Orchestrating parallel execution with synthesis for {len(agents)} agents")
        
        # Execute agents in parallel
        parallel_result = await self.execute_parallel_agents(
            agents, conv, authorization, image_data
        )
        
        if not parallel_result.success:
            logger.error("Parallel execution failed")
            return AggregatedResponse(
                success=False,
                synthesized_response=f"Parallel execution failed: {parallel_result.error}",
                source_agents=[],
                successful_count=0,
                failed_count=0,
                synthesis_duration=0.0,
                total_duration=0.0,
                fallback_used=True,
                error=parallel_result.error
            )
        
        # Synthesize responses
        aggregated = await self.synthesize_responses(parallel_result, user_query)
        
        return aggregated
    
    # =========================================================================
    # Sequential Streaming (for WebSocket)
    # =========================================================================
    
    async def stream_agents_sequentially(
        self,
        agents: List,
        conv,
        authorization: Optional[str] = None,
        websocket = None,
        conv_manager = None
    ) -> Dict[str, str]:
        """
        Stream agent responses sequentially over WebSocket.
        
        Used for WebSocket connections where responses need to be streamed
        as they become available rather than collected and aggregated.
        
        Args:
            agents: List of agent instances
            conv: Conversation context
            authorization: Authorization header/token
            websocket: WebSocket connection for streaming
            conv_manager: Conversation manager for processing directives
            
        Returns:
            Dictionary mapping agent names to their responses
        """
        try:
            logger.info(f"Starting sequential streaming for {len(agents)} agents")
            
            all_responses = {}
            
            for idx, agent in enumerate(agents, 1):
                logger.debug(f"[{idx}/{len(agents)}] Streaming from: {agent.name}")
                
                try:
                    response_content = ""
                    
                    # Send agent header
                    if websocket:
                        agent_header = f"\n{'='*60}\n[Agent {idx}/{len(agents)}] {agent.name}\n{'='*60}\n"
                        await websocket.send_text(agent_header)
                    
                    # Stream response from agent
                    async for content in agent.invoke_stream(conv, authorization=authorization):
                        try:
                            # Try to parse as extra data
                            extra_data: ExtraData = ExtraData.new_from_json(content)
                            if conv_manager:
                                context_directives = parse_context_directives(extra_data)
                                await conv_manager.process_context_directives(conv, context_directives)
                        except Exception:
                            # Not extra data, stream as regular content
                            response_content = f"{response_content}{content}"
                            if websocket:
                                await websocket.send_text(content)
                    
                    all_responses[agent.name] = response_content
                    logger.debug(f"Completed streaming from: {agent.name}")
                    
                except Exception as e:
                    logger.error(f"Streaming failed for {agent.name}: {e}")
                    error_msg = f"Error from {agent.name}: {str(e)}\n"
                    all_responses[agent.name] = error_msg
                    if websocket:
                        await websocket.send_text(error_msg)
            
            logger.info("Sequential streaming complete")
            return all_responses
            
        except Exception as e:
            logger.error(f"Sequential streaming failed: {e}", exc_info=True)
            return {}


def create_orchestration_service(
    openai_client: Optional[AzureOpenAIClient] = None
) -> AgentOrchestrationService:
    """
    Factory function to create agent orchestration service.
    
    Args:
        openai_client: Optional pre-configured OpenAI client
        
    Returns:
        Configured AgentOrchestrationService instance
    """
    if openai_client is None:
        from integration.openai_client import create_azure_openai_client
        openai_client = create_azure_openai_client()
    
    return AgentOrchestrationService(openai_client=openai_client)
