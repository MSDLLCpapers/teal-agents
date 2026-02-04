import logging

from typing import Optional

from ska_utils import AppConfig
from agents import RecipientChooserAgent
from configs import (
    TA_ENABLE_SEMANTIC_SEARCH,
    TA_SEMANTIC_SEARCH_TOP_K,
    TA_SEMANTIC_SEARCH_THRESHOLD,
    TA_ENABLE_QUERY_EXPANSION,
    TA_ENABLE_FOLLOWUP_ANALYSIS,
    TA_FOLLOWUP_MAX_HISTORY,
    TA_ENABLE_PARALLEL_PROCESSING,
    TA_PARALLEL_MAX_AGENTS,
)
from integration.chroma_client import ChromaClient
from model import Conversation
from model.recipient_chooser import ReqAgent, SelectedAgent
from services.hybrid_search_service import HybridSearchService

logger = logging.getLogger(__name__)


def _normalize_agent_type(value: object) -> str | None:
    """Helper function to normalize agent type strings."""
    if not value:
        return None
    text = str(value).strip().lower()
    if text in {"knowledge", "action"}:
        return text
    if "knowledge" in text:
        return "knowledge"
    if "action" in text:
        return "action"
    return None


# ============================================================================
# Recipient Chooser
# ============================================================================

class RecipientChooser:
    """RecipientChooser

    Chooses which agent should handle the next message in a conversation.
    Uses semantic search to filter agent list to top-N matches before LLM selection.
    """

    def __init__(
        self,
        agent: RecipientChooserAgent,
        hybrid_search_service: Optional[HybridSearchService],
        chroma_client: Optional[ChromaClient] = None
    ):
        self.agent = agent
        self.hybrid_search_service = hybrid_search_service
        self.chroma_client = chroma_client
        
        # Load agent list from agents_registry database table
        self.agent_list: list[ReqAgent] = self._load_agents_from_database()
        
        # Semantic search configuration using AppConfig
        app_config = AppConfig()
        self.enable_semantic_search = app_config.get(TA_ENABLE_SEMANTIC_SEARCH.env_name).lower() == "true"
        self.semantic_search_top_k = int(app_config.get(TA_SEMANTIC_SEARCH_TOP_K.env_name))
        self.semantic_search_threshold = float(app_config.get(TA_SEMANTIC_SEARCH_THRESHOLD.env_name))
        
        # Query expansion configuration
        self.enable_query_expansion = app_config.get(TA_ENABLE_QUERY_EXPANSION.env_name).lower() == "true"
        
        # Follow-up analysis configuration
        self.enable_followup_analysis = app_config.get(TA_ENABLE_FOLLOWUP_ANALYSIS.env_name).lower() == "true"
        self.followup_max_history = int(app_config.get(TA_FOLLOWUP_MAX_HISTORY.env_name))
        
        # Parallel processing configuration
        self.enable_parallel_processing = app_config.get(TA_ENABLE_PARALLEL_PROCESSING.env_name).lower() == "true"
        self.parallel_max_agents = int(app_config.get(TA_PARALLEL_MAX_AGENTS.env_name))
        
        logger.info(f"RecipientChooser initialized")
        logger.info(f"Semantic search: {'ENABLED' if self.enable_semantic_search else 'DISABLED'}")
        if self.enable_semantic_search:
            logger.info(f"- Top K: {self.semantic_search_top_k}")
            logger.info(f"- Threshold: {self.semantic_search_threshold}")
        logger.info(f"Follow-up analysis: {'ENABLED' if self.enable_followup_analysis else 'DISABLED'}")
        if self.enable_followup_analysis:
            logger.info(f"- Max history messages: {self.followup_max_history}")
        logger.info(f"Parallel processing: {'ENABLED' if self.enable_parallel_processing else 'DISABLED'}")
        if self.enable_parallel_processing:
            logger.info(f"- Max parallel agents: {self.parallel_max_agents}")

    def _load_agents_from_database(self) -> list[ReqAgent]:
        """
        Load active agents from ChromaDB collection.
        Returns list of ReqAgent objects with name, description, and (if available) type.
        """
        # If no ChromaClient is available, fallback to agent catalog
        if self.chroma_client is None:
            logger.warning("ChromaClient not available, falling back to agent catalog")
            return self._fallback_to_agent_catalog()
        
        try:
            logger.info("Loading agents from ChromaDB collection...")
            
            # Get all agents from collection using ChromaClient
            all_agents = self.chroma_client.get_all_documents()
            
            agents = []
            for i, agent_id in enumerate(all_agents['ids']):
                metadata = all_agents['metadatas'][i] or {}
                agent_name = metadata.get('name', agent_id)
                description = metadata.get('description', all_agents['documents'][i])
                agent_type = _normalize_agent_type(metadata.get('type') or metadata.get('agent_type'))

                agents.append(ReqAgent(name=agent_name, description=description, type=agent_type))
                logger.info(f"Loaded agent: {agent_name}")
            
            logger.info(f"Loaded {len(agents)} agents from ChromaDB")
            
            if not agents:
                logger.warning("No agents found in ChromaDB, falling back to agent catalog")
                return self._fallback_to_agent_catalog()
            
            return agents
            
        except Exception as e:
            logger.error(f"Failed to load agents from ChromaDB: {e}", exc_info=True)
            logger.warning("Falling back to agent catalog")
            return self._fallback_to_agent_catalog()

    def _fallback_to_agent_catalog(self) -> list[ReqAgent]:
        """Fallback method to load agents from agent catalog."""
        try:
            return [
                ReqAgent(
                    name=agent.name,
                    description=agent.description,
                    type=_normalize_agent_type(getattr(agent, 'type', None))
                )
                for agent in self.agent.agent_catalog.agents.values()
            ]
        except Exception as fallback_error:
            logger.error(f"Fallback to agent catalog also failed: {fallback_error}")
            return []

    async def choose_recipient(self, message: str, conv: Conversation, authorization: str | None = None) -> SelectedAgent:
        """Chooses the recipient

        Args:
            message (str): The current message from the client
            conv (Conversation): The conversation history, so far
        Returns:
            The name of the agent that should handle the message
        """
        # Start with full agent list
        filtered_agent_list = self.agent_list
        
        # Try semantic search first to filter to top-N agents (only if enabled AND service is available)
        if self.enable_semantic_search and self.hybrid_search_service is not None:
            try:
                logger.info("=" * 80)
                logger.info("SEMANTIC SEARCH - Agent Filtering")
                
                # Perform follow-up analysis if enabled (query expansion)
                search_query = message
                followup_result = None
                if self.enable_followup_analysis:
                    try:
                        agents_registry_for_intent = [
                            {"name": agent.name, "type": agent.type}
                            for agent in self.agent_list
                            if agent.type
                        ]
                        followup_result = self.hybrid_search_service.analyze_followup(
                            current_message=message,
                            conversation_history=[
                                {'content': getattr(msg, 'content', str(msg)), 
                                 'sender': getattr(msg, 'sender', 'Unknown'),
                                 'recipient': getattr(msg, 'recipient', 'Unknown')}
                                for msg in conv.history
                            ] if conv.history else [],
                            agents_registry=agents_registry_for_intent,
                            max_history_messages=self.followup_max_history
                        )
                        search_query = followup_result.expanded_query
                        logger.info(f"Query: '{message}' → '{search_query}'")
                        logger.info(f"Is Follow-up: {followup_result.is_followup}")
                    except Exception as followup_error:
                        logger.warning(f"Follow-up analysis failed: {followup_error}")
                        search_query = message
                        followup_result = None
                
                # Search for ALL agents to get full confidence scores (not just top-k)
                search_results = self.hybrid_search_service.search_agents(
                    query=search_query,
                    top_k=10,  # Get all agents
                    confidence_threshold=0.0  # No threshold filtering yet
                )
                
                if search_results: 
                    # sending top 5 to the reranker LLM    
                    top_search_results = search_results[:5]
                    
                    # Standard single-agent selection with LLM reranker
                    if top_search_results:
                        logger.info(f"Candidates from semantic search:")
                        for result in top_search_results:
                            logger.info(f"{result.agent_name}: ({result.bm25_score:.3f}×0.25) + ({result.semantic_score:.3f}×0.75) = {result.confidence:.3f}")
                        
                        # Filter out GeneralAgent unless query is a pure greeting
                        greeting_keywords = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
                        message_lower = message.lower().strip()
                        is_pure_greeting = any(message_lower == kw or message_lower.startswith(kw + ' ') or message_lower.startswith(kw + ',') for kw in greeting_keywords) and len(message.split()) <= 5
                        
                        if not is_pure_greeting:
                            top_search_results = [r for r in top_search_results if 'GeneralAgent' not in r.agent_name]
                        
                        logger.info(f"Using LLM reranker for final selection...")
                        
                        # Prepare candidate list for reranker
                        reranker_candidates = [result.to_candidate() for result in top_search_results]
                        
                        # Prepare scores list for guidance
                        agent_scores_list = [result.to_score() for result in top_search_results]
                        
                        selected_agent = await self.hybrid_search_service.select_agent_with_reranker(
                            candidate_agents=reranker_candidates,
                            message=message,
                            conversation_context=conv,
                            agent_scores=agent_scores_list,
                            followup_analysis=followup_result
                        )
                        
                        return selected_agent
                    else:
                        logger.warning("Low semantic confidence, using full agent list")
                        filtered_agent_list = self.agent_list
                else:
                    logger.warning("Semantic search returned no results, using full agent list")
                    
            except Exception as e:
                logger.error(f"Semantic search error: {e}", exc_info=True)
                logger.warning("Falling back to full agent list")
                filtered_agent_list = self.agent_list
        
        # Check if hybrid_search_service is available for LLM reranker
        if self.hybrid_search_service is None:
            # Fallback: use simple agent selection from agent catalog (first matching agent)
            logger.warning("HybridSearchService not available - using fallback agent selection")
            if filtered_agent_list:
                first_agent = filtered_agent_list[0]
                return SelectedAgent(
                    agent_name=first_agent.name,
                    primary_agent=first_agent.name,
                    secondary_agent=None,
                    confidence="medium",
                    is_followup=False,
                    is_parallel=False,
                    parallel_agents=[],
                    parallel_reason=""
                )
            else:
                # No agents available
                return SelectedAgent(
                    agent_name="fallback",
                    primary_agent="fallback",
                    secondary_agent=None,
                    confidence="low",
                    is_followup=False,
                    is_parallel=False,
                    parallel_agents=[],
                    parallel_reason=""
                )
        
        # Use LLM reranker for agent selection (replaces agent selector agent API call): 
        print("=" * 80, flush=True)
        print("LLM RERANKER - Selecting best agent from candidates...", flush=True)
        print(f"Agents in selection pool: {len(filtered_agent_list)}", flush=True)
        print("=" * 80, flush=True)
        
        logger.info("=" * 80)
        logger.info("LLM RERANKER - Agent Selection")
        logger.info(f"Candidate count: {len(filtered_agent_list)}")
        
        # Perform follow-up analysis if not already done by semantic search
        followup_result = None
        if self.enable_followup_analysis:
            try:
                followup_result = self.hybrid_search_service.analyze_followup(
                    current_message=message,
                    conversation_history=[
                        {'content': getattr(msg, 'content', str(msg)), 
                         'sender': getattr(msg, 'sender', 'Unknown'),
                         'recipient': getattr(msg, 'recipient', 'Unknown')}
                        for msg in conv.history
                    ] if conv.history else [],
                    max_history_messages=self.followup_max_history
                )
                logger.info(f"Follow-up analysis completed")
                logger.info(f"Is Follow-up: {followup_result.is_followup}")
            except Exception as followup_error:
                logger.warning(f"Follow-up analysis failed: {followup_error}")
                followup_result = None
        
        # Prepare candidate list for reranker (convert ReqAgent to dict format)
        reranker_candidates = [
            {'name': agent.name, 'description': agent.description}
            for agent in filtered_agent_list
        ]
        
        # Use service's reranker with followup analysis
        selected_agent = await self.hybrid_search_service.select_agent_with_reranker(
            candidate_agents=reranker_candidates,
            message=message,
            conversation_context=conv,
            followup_analysis=followup_result
        )
        
        return selected_agent
    
    def resolve_agents(
        self,
        selected_agent: SelectedAgent,
        agent_catalog,
        fallback_agent
    ) -> tuple[list, str]:
        """
        Resolve selected agent names to actual agent instances.
        
        Args:
            selected_agent: Result from choose_recipient()
            agent_catalog: Catalog of available agents
            fallback_agent: Fallback agent if primary not found
            
        Returns:
            Tuple of (list of agents to invoke, primary agent name)
        """
        agents_to_invoke = []
        primary_agent_name = selected_agent.agent_name
        
        # Get primary agent
        if selected_agent.agent_name in agent_catalog.agents:
            primary_agent = agent_catalog.agents[selected_agent.agent_name]
            agents_to_invoke.append(primary_agent)
        else:
            logger.warning(f"Primary agent '{selected_agent.agent_name}' not found, using fallback")
            agents_to_invoke.append(fallback_agent)
            primary_agent_name = fallback_agent.name
        
        # Get parallel agents if needed
        if selected_agent.is_parallel and selected_agent.parallel_agents:
            logger.debug(f"Adding {len(selected_agent.parallel_agents)} parallel agents")
            for parallel_agent_name in selected_agent.parallel_agents:
                # Try case-insensitive match
                agent_found = None
                for catalog_key, catalog_agent in agent_catalog.agents.items():
                    if catalog_key.lower() == parallel_agent_name.lower():
                        agent_found = catalog_agent
                        break
                
                if agent_found:
                    agents_to_invoke.append(agent_found)
                    logger.debug(f"Added parallel agent: {parallel_agent_name}")
                else:
                    logger.warning(f"Parallel agent '{parallel_agent_name}' not found in catalog")
        
        # Handle secondary_agent for backward compatibility (websockets)
        if selected_agent.secondary_agent and not selected_agent.is_parallel:
            for catalog_key, catalog_agent in agent_catalog.agents.items():
                if catalog_key.lower() == selected_agent.secondary_agent.lower():
                    agents_to_invoke.append(catalog_agent)
                    logger.debug(f"Added secondary agent: {selected_agent.secondary_agent}")
                    break
        
        logger.debug(f"Total agents to invoke: {len(agents_to_invoke)}")
        return agents_to_invoke, primary_agent_name

