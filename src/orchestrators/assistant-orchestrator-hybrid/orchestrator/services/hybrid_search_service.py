"""
Hybrid Search Service for Agent Selection.

This module provides the main hybrid search service that combines:
- BM25 lexical matching
- Semantic similarity via ChromaDB
- LLM-based reranking and follow-up analysis
"""

import logging
import re
from typing import List, Dict, Any, Optional

from rank_bm25 import BM25Okapi
from ska_utils import AppConfig

from configs import AZURE_OPENAI_RERANKER_MODEL, AZURE_OPENAI_CHAT_MODEL
from integration.postgres_client import PostgresClient
from integration.openai_client import AzureOpenAIClient
from model.search import AgentSearchResult, SemanticSearchResult, AgentCorpusEntry
from model.recipient_chooser import FollowUpAnalysisResult, SelectedAgent
from prompts.query_analysis import (
    QUERY_ANALYSIS_SYSTEM_PROMPT,
    QUERY_EXPANSION_SYSTEM_PROMPT,
    build_followup_analysis_prompt,
    build_query_expansion_prompt,
    format_conversation_history,
    build_agent_registry_text,
)
from prompts.agent_selection import (
    AGENT_SELECTION_SYSTEM_PROMPT,
    build_agent_selection_prompt,
    build_agents_text,
    build_semantic_scores_text,
    build_conversation_context,
)

logger = logging.getLogger(__name__)


class HybridSearchService:
    """
    Hybrid search service combining BM25 and semantic search.
    
    This service provides:
    1. Semantic search via PostgreSQL + pgvector with embeddings
    2. BM25 lexical matching for keyword-based search
    3. Hybrid scoring with configurable weights
    4. LLM-based query expansion and follow-up analysis
    5. LLM-based agent reranking
    """
    
    def __init__(
        self,
        postgres_client: PostgresClient,
        openai_client: AzureOpenAIClient,
        bm25_weight: float = 0.25,
        semantic_weight: float = 0.75
    ):
        """
        Initialize hybrid search service.
        
        Args:
            postgres_client: PostgreSQL client instance
            openai_client: Azure OpenAI client instance
            bm25_weight: Weight for BM25 scores (default: 0.25)
            semantic_weight: Weight for semantic scores (default: 0.75)
        """
        self.postgres_client = postgres_client
        self.openai_client = openai_client
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight
        
        # Initialize BM25 index
        self.agent_corpus: List[AgentCorpusEntry] = []
        self.bm25_index: Optional[BM25Okapi] = None
        self._initialize_bm25()
        
        logger.info(f"HybridSearchService initialized")
        logger.info(f"Weights: BM25={bm25_weight}, Semantic={semantic_weight}")
    
    def _initialize_bm25(self) -> None:
        """Initialize BM25 index from PostgreSQL database."""
        try:
            # Get all documents from PostgreSQL
            all_docs = self.postgres_client.get_all_documents()
            
            tokenized_corpus = []
            
            for i, doc_id in enumerate(all_docs['ids']):
                metadata = all_docs['metadatas'][i] or {}
                agent_name = metadata.get('agent_name', doc_id)
                description = all_docs['documents'][i]
                keywords = metadata.get('keywords', [])
                
                # Combine description and keywords
                if isinstance(keywords, str):
                    import json
                    keywords = json.loads(keywords) if keywords.startswith('[') else [keywords]
                
                full_text = description + " " + " ".join(keywords)
                tokens = re.findall(r'\w+', full_text.lower())
                
                corpus_entry = AgentCorpusEntry(
                    agent_name=agent_name,
                    description=description,
                    tokens=tokens,
                    metadata=metadata
                )
                self.agent_corpus.append(corpus_entry)
                tokenized_corpus.append(tokens)
            
            # Build BM25 index
            if tokenized_corpus:
                self.bm25_index = BM25Okapi(tokenized_corpus)
                logger.info(f"BM25 index built with {len(self.agent_corpus)} agents")
            else:
                logger.warning("No agents found for BM25 index")
                
        except Exception as e:
            logger.error(f"Failed to initialize BM25: {e}")
            raise
    
    def _calculate_bm25_scores(self, query_text: str) -> Dict[str, float]:
        """
        Calculate BM25 scores for all agents.
        
        Args:
            query_text: The search query text
            
        Returns:
            Dictionary mapping agent_name to normalized BM25 score (0-1)
        """
        try:
            if not self.bm25_index or not self.agent_corpus:
                logger.warning("BM25 index not available")
                return {}
            
            # Tokenize query
            query_tokens = re.findall(r'\w+', query_text.lower())
            
            if not query_tokens:
                logger.warning("No valid tokens in query for BM25")
                return {}
            
            # Get BM25 scores
            raw_scores = self.bm25_index.get_scores(query_tokens)
            max_score = max(raw_scores) if max(raw_scores) > 0 else 1.0
            
            bm25_scores = {}
            for i, agent_entry in enumerate(self.agent_corpus):
                normalized_score = raw_scores[i] / max_score
                if normalized_score > 0:
                    bm25_scores[agent_entry.agent_name] = float(normalized_score)
            
            logger.debug(f"BM25 scores calculated for {len(bm25_scores)} agents")
            return bm25_scores
            
        except Exception as e:
            logger.error(f"Failed to calculate BM25 scores: {e}")
            return {}
    
    def _calculate_semantic_scores(
        self,
        query: str,
        top_k: int = 10
    ) -> List[SemanticSearchResult]:
        """
        Calculate semantic similarity scores using PostgreSQL + pgvector.
        
        Args:
            query: The search query
            top_k: Number of top results to return
            
        Returns:
            List of SemanticSearchResult objects
        """
        try:
            results_with_scores = self.postgres_client.similarity_search_with_score(
                query=query,
                k=top_k
            )
            
            semantic_results = []
            for doc, score in results_with_scores:
                # pgvector returns normalized similarity score (already 0-1 range from PostgresClient)
                similarity_score = score
                
                agent_name = doc.metadata.get('agent_name', 'Unknown')
                description = doc.page_content
                
                result = SemanticSearchResult(
                    agent_name=agent_name,
                    description=description,
                    semantic_score=float(similarity_score),
                    metadata=doc.metadata
                )
                semantic_results.append(result)
            
            logger.debug(f"Semantic scores calculated for {len(semantic_results)} agents")
            return semantic_results
            
        except Exception as e:
            logger.error(f"Failed to calculate semantic scores: {e}")
            return []
    
    def _combine_hybrid_scores(
        self,
        semantic_results: List[SemanticSearchResult],
        bm25_scores: Dict[str, float]
    ) -> List[AgentSearchResult]:
        """
        Combine BM25 and semantic scores with weights.
        
        Args:
            semantic_results: List of semantic search results
            bm25_scores: Dictionary mapping agent_name to bm25_score
        
        Returns:
            List of AgentSearchResult objects sorted by confidence
        """
        results = []
        
        for sem_result in semantic_results:
            agent_name = sem_result.agent_name
            semantic_score = sem_result.semantic_score
            bm25_score = bm25_scores.get(agent_name, 0.0)
            
            # Weighted hybrid score
            hybrid_score = (
                self.bm25_weight * bm25_score +
                self.semantic_weight * semantic_score
            )
            
            result = AgentSearchResult(
                agent_name=agent_name,
                description=sem_result.description,
                confidence=float(hybrid_score),
                bm25_score=float(bm25_score),
                semantic_score=float(semantic_score),
                metadata=sem_result.metadata
            )
            results.append(result)
            
            logger.debug(
                f"{agent_name}: ({bm25_score:.3f}×{self.bm25_weight}) + "
                f"({semantic_score:.3f}×{self.semantic_weight}) = {hybrid_score:.3f}"
            )
        
        return sorted(results, key=lambda x: x.confidence, reverse=True)
    
    def _preprocess_query(self, query: str) -> str:
        """Clean and normalize user query before search."""
        original_query = query
        
        # Remove URLs
        query = re.sub(
            r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+',
            '', query
        )
        
        # Remove email addresses
        query = re.sub(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '', query)
        
        # Remove excessive punctuation
        query = re.sub(r'([!?.]){2,}', r'\1', query)
        
        # Remove special characters
        query = re.sub(r'[#@$%^&*()_+=\[\]{};:"\|<>/~`]', ' ', query)
        
        # Normalize whitespace
        query = ' '.join(query.split()).strip()
        
        if not query:
            logger.warning(f"Query became empty after preprocessing: '{original_query}'")
            return original_query
        
        if query != original_query:
            logger.info(f"Query preprocessed: '{original_query}' → '{query}'")
        
        return query
    
    def search_agents(
        self,
        query: str,
        top_k: int = 10,
        confidence_threshold: float = 0.0
    ) -> List[AgentSearchResult]:
        """
        Search for relevant agents using hybrid BM25 + semantic matching.
        
        Args:
            query: User's message/query
            top_k: Number of top results to return
            confidence_threshold: Minimum confidence score (0-1)
        
        Returns:
            List of AgentSearchResult objects
        """
        try:
            logger.info("=" * 80)
            logger.info("HYBRID AGENT SEARCH - Starting")
            logger.info(f"Query: '{query}'")
            logger.info(f"Weights: BM25={self.bm25_weight}, Semantic={self.semantic_weight}")
            
            # Preprocess query
            preprocessed_query = self._preprocess_query(query)
            
            # Calculate semantic scores
            logger.info("Calculating semantic scores...")
            semantic_results = self._calculate_semantic_scores(preprocessed_query, top_k)
            
            if not semantic_results:
                logger.warning("No agents found in semantic search")
                return []
            
            # Calculate BM25 scores
            logger.info("Calculating BM25 scores...")
            bm25_scores = self._calculate_bm25_scores(preprocessed_query)
            
            # Combine hybrid scores
            logger.info("Combining hybrid scores...")
            hybrid_results = self._combine_hybrid_scores(semantic_results, bm25_scores)
            
            # Filter by threshold
            filtered_results = [
                r for r in hybrid_results if r.confidence >= confidence_threshold
            ][:top_k]
            
            logger.info("=" * 80)
            logger.info(f"RESULTS: {len(filtered_results)} agents selected")
            for idx, result in enumerate(filtered_results, 1):
                logger.info(
                    f"{idx}. {result.agent_name}: "
                    f"({result.bm25_score:.3f}×{self.bm25_weight}) + "
                    f"({result.semantic_score:.3f}×{self.semantic_weight}) = "
                    f"{result.confidence:.3f}"
                )
            logger.info("=" * 80)
            
            return filtered_results
            
        except Exception as e:
            logger.error(f"Hybrid search failed: {e}", exc_info=True)
            return []
    
    def analyze_followup(
        self,
        current_message: str,
        conversation_history: List[dict],
        agents_registry: Optional[List[dict]] = None,
        max_history_messages: int = 2,
        enable_query_expansion: bool = True
    ) -> FollowUpAnalysisResult:
        """
        Analyze if message is follow-up and expand query.
        
        Args:
            current_message: The current user message
            conversation_history: List of previous messages
            agents_registry: List of agent metadata dicts
            max_history_messages: Maximum number of recent messages to consider
            enable_query_expansion: Whether to expand query
        
        Returns:
            FollowUpAnalysisResult with analysis details
        """
        try:
            logger.info("FOLLOW-UP ANALYSIS - Starting")
            logger.info(f"Message: '{current_message}'")
            
            # No history - just do query expansion
            if not conversation_history:
                logger.info("No history - performing query expansion only")
                return self._expand_query_only(
                    query=current_message,
                    enable_expansion=enable_query_expansion,
                    agents_registry=agents_registry
                )
            
            # Get recent history
            recent_history = conversation_history[-max_history_messages:]
            history_text = format_conversation_history(recent_history)
            agent_registry_text = build_agent_registry_text(agents_registry)
            
            # Build prompt and call LLM
            prompt = build_followup_analysis_prompt(
                current_message=current_message,
                history_text=history_text,
                agent_registry_text=agent_registry_text
            )
            
            result_json = self.openai_client.chat_completion_json(
                system_prompt=QUERY_ANALYSIS_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=800
            )
            
            # Parse result
            result = FollowUpAnalysisResult(
                is_followup=bool(result_json.get("is_followup", False)),
                original_query=result_json.get("original_query", current_message),
                expanded_query=result_json.get("expanded_query", current_message),
                key_terms_added=result_json.get("key_terms_added", []),
                reasoning=result_json.get("reasoning", "N/A"),
                intent=result_json.get("intent", "knowledge")
            )
            
            logger.info(f"Is Follow-up: {result.is_followup}")
            logger.info(f"Expanded: '{result.expanded_query}'")
            logger.info(f"Intent: {result.intent}")
            
            return result
            
        except Exception as e:
            logger.error(f"Follow-up analysis failed: {e}", exc_info=True)
            return FollowUpAnalysisResult(
                is_followup=False,
                original_query=current_message,
                expanded_query=current_message,
                key_terms_added=[],
                reasoning="fallback_due_to_error",
                intent="knowledge"
            )
    
    def _expand_query_only(
        self,
        query: str,
        enable_expansion: bool,
        agents_registry: Optional[List[dict]] = None
    ) -> FollowUpAnalysisResult:
        """Expand query when there's no conversation history."""
        if not enable_expansion:
            return FollowUpAnalysisResult(
                is_followup=False,
                original_query=query,
                expanded_query=query,
                key_terms_added=[],
                reasoning="query_expansion_disabled",
                intent="knowledge"
            )
        
        try:
            agent_registry_text = build_agent_registry_text(agents_registry)
            prompt = build_query_expansion_prompt(query, agent_registry_text)
            
            result_json = self.openai_client.chat_completion_json(
                system_prompt=QUERY_EXPANSION_SYSTEM_PROMPT,
                user_prompt=prompt,
                temperature=0.3,
                max_tokens=400
            )
            
            result = FollowUpAnalysisResult(
                is_followup=False,
                original_query=query,
                expanded_query=result_json.get("expanded_query", query),
                key_terms_added=result_json.get("key_terms_added", []),
                reasoning=result_json.get("reasoning", "N/A"),
                intent=result_json.get("intent", "knowledge")
            )
            
            logger.info(f"Query expanded: '{query}' → '{result.expanded_query}'")
            return result
            
        except Exception as e:
            logger.error(f"Query expansion failed: {e}", exc_info=True)
            return FollowUpAnalysisResult(
                is_followup=False,
                original_query=query,
                expanded_query=query,
                key_terms_added=[],
                reasoning="fallback_due_to_error",
                intent="knowledge"
            )
    
    async def select_agent_with_reranker(
        self,
        candidate_agents: List[dict],
        message: str,
        conversation_context: Any,
        agent_scores: Optional[List[dict]] = None,
        followup_analysis: Optional[FollowUpAnalysisResult] = None
    ) -> SelectedAgent:
        """
        Select best agent using LLM reranker.
        
        Args:
            candidate_agents: List of agent dicts with 'name' and 'description'
            message: User's message
            conversation_context: Conversation object with history
            agent_scores: Optional list of agents with semantic confidence scores
            followup_analysis: Optional FollowUpAnalysisResult
            
        Returns:
            SelectedAgent with selection details
        """
        try:
            # Build prompt components
            agents_text = build_agents_text(candidate_agents, agent_scores)
            semantic_scores_text = build_semantic_scores_text(agent_scores or [], candidate_agents)
            conv_context = build_conversation_context(followup_analysis, conversation_context.history if hasattr(conversation_context, 'history') else None)
            
            # Build complete prompt
            prompt = build_agent_selection_prompt(
                agents_text=agents_text,
                semantic_scores_text=semantic_scores_text,
                conv_context=conv_context,
                message=message
            )
            
            # Call LLM reranker
            # Get reranker model from config, fallback to chat model if not set
            app_config = AppConfig()
            reranker_model = app_config.get(AZURE_OPENAI_RERANKER_MODEL.env_name) or app_config.get(AZURE_OPENAI_CHAT_MODEL.env_name)
            logger.info(f"Calling LLM reranker (model: {reranker_model})")
            logger.info(f"Candidates: {[a['name'] for a in candidate_agents]}")
            
            result_json = self.openai_client.chat_completion_json(
                system_prompt=AGENT_SELECTION_SYSTEM_PROMPT,
                user_prompt=prompt,
                model=reranker_model,
                temperature=0.4,
                max_tokens=200
            )
            
            # Extract and validate agent names
            def ensure_version_tag(agent_name: str) -> str:
                """Ensure agent name has version tag."""
                if ":" in agent_name:
                    return agent_name
                # Find matching candidate
                base_name = agent_name.split(":")[0]
                for candidate in candidate_agents:
                    if candidate["name"].split(":")[0] == base_name:
                        return candidate["name"]
                return agent_name
            
            primary_agent = ensure_version_tag(result_json["primary_agent"])
            secondary_agent = ensure_version_tag(result_json["secondary_agent"]) if result_json.get("secondary_agent") else None
            
            selected = SelectedAgent(
                agent_name=primary_agent,
                primary_agent=primary_agent,
                secondary_agent=secondary_agent,
                confidence=result_json["confidence"],
                is_followup=result_json.get("is_followup", False),
                is_parallel=False,
                parallel_agents=[],
                parallel_reason=""
            )
            
            logger.info(f"Selected: {selected.agent_name} (confidence: {selected.confidence})")
            if secondary_agent:
                logger.info(f"Secondary: {secondary_agent}")
            
            return selected
            
        except Exception as e:
            logger.error(f"LLM reranker failed: {e}", exc_info=True)
            # Fallback to first candidate
            return SelectedAgent(
                agent_name=candidate_agents[0]["name"],
                primary_agent=candidate_agents[0]["name"],
                secondary_agent=candidate_agents[1]["name"] if len(candidate_agents) > 1 else None,
                confidence="Low",
                is_followup=False,
                is_parallel=False,
                parallel_agents=[],
                parallel_reason=""
            )
