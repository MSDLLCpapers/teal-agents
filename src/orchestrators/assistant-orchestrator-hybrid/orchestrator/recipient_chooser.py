import json
import logging
import os
import re

import chromadb
from chromadb.config import Settings

from openai import AzureOpenAI
from pydantic import BaseModel, ConfigDict, Field
from rank_bm25 import BM25Okapi
from typing import Optional, List, Dict, Any, Literal

from agents import RecipientChooserAgent
from model import Conversation

logger = logging.getLogger(__name__)


# ============================================================================
# Data Models
# ============================================================================

class FollowUpAnalysisResult(BaseModel):
    """Result from follow-up analysis with query expansion."""
    is_followup: bool
    original_query: str
    expanded_query: str
    key_terms_added: list[str] = Field(default_factory=list)
    reasoning: str = ""
    intent: Literal["knowledge", "action"] = "knowledge"


def _normalize_agent_type(value: object) -> str | None:
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
# ChromaDB + LangChain Service for Agent Selection
# ============================================================================

class ChromaDBSearchService:
    """
    Semantic search service using ChromaDB + LangChain for agent selection.
    Combines BM25 (lexical) and semantic similarity for accurate agent matching.
    
    Scoring Formula: score = (BM25 × 0.25) + (Semantic × 0.75)
    """
    
    def __init__(
        self,
        persist_directory: str = "./chroma_agents",
        collection_name: str = "agents_registry",
        embedding_model: str = "text-embedding-3-small",
        bm25_weight: float = 0.25,
        semantic_weight: float = 0.75
    ):
        """
        Initialize ChromaDB search service with LangChain.
        
        Args:
            persist_directory: Directory to persist ChromaDB data
            collection_name: Name of the ChromaDB collection
            embedding_model: Azure OpenAI embedding model name
            bm25_weight: Weight for BM25 lexical matching (default: 0.25)
            semantic_weight: Weight for semantic similarity (default: 0.75)
        """
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.embedding_model = embedding_model
        self.bm25_weight = bm25_weight
        self.semantic_weight = semantic_weight
        
        # Azure OpenAI configuration
        self.openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        
        if not self.openai_api_key or not self.openai_endpoint:
            raise ValueError("Azure OpenAI API key and endpoint are required")
        
        # Initialize ChromaDB and LangChain components
        self._initialize_chromadb()
        self._initialize_bm25()
        
        logger.info(f"ChromaDBSearchService initialized")
        logger.info(f"Collection: {collection_name}")
        logger.info(f"Weights: bm25={bm25_weight}, semantic={semantic_weight}")
        logger.info(f"Embedding model: {embedding_model}")
    
    def _initialize_chromadb(self):
        """Initialize ChromaDB client and collection with LangChain."""
        try:
            from langchain_openai import AzureOpenAIEmbeddings
            from langchain_community.vectorstores import Chroma
            
            # Initialize Azure OpenAI embeddings via LangChain
            self.embeddings = AzureOpenAIEmbeddings(
                azure_deployment=self.embedding_model,
                openai_api_version=self.openai_api_version,
                azure_endpoint=self.openai_endpoint,
                api_key=self.openai_api_key
            )
            
            # Initialize ChromaDB client
            self.chroma_client = chromadb.PersistentClient(
                path=self.persist_directory,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Initialize LangChain Chroma vectorstore
            self.vectorstore = Chroma(
                client=self.chroma_client,
                collection_name=self.collection_name,
                embedding_function=self.embeddings
            )
            
            # Get collection stats
            collection = self.chroma_client.get_collection(name=self.collection_name)
            agent_count = collection.count()
            
            logger.info(f"ChromaDB initialized successfully")
            logger.info(f"Persist directory: {self.persist_directory}")
            logger.info(f"Agents in collection: {agent_count}")
            
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            raise
    
    def _initialize_bm25(self):
        """Initialize BM25 index from ChromaDB collection."""
        try:
            
            # Get all documents from ChromaDB
            collection = self.chroma_client.get_collection(name=self.collection_name)
            all_docs = collection.get(include=["documents", "metadatas"])
            
            self.agent_corpus = []
            tokenized_corpus = []
            
            for i, doc_id in enumerate(all_docs['ids']):
                agent_name = all_docs['metadatas'][i].get('agent_name', doc_id)
                description = all_docs['documents'][i]
                keywords = all_docs['metadatas'][i].get('keywords', [])
                
                # Combine description and keywords
                if isinstance(keywords, str):
                    keywords = json.loads(keywords) if keywords.startswith('[') else [keywords]
                
                full_text = description + " " + " ".join(keywords)
                tokens = re.findall(r'\w+', full_text.lower())
                
                self.agent_corpus.append({
                    'agent_name': agent_name,
                    'description': description,
                    'tokens': tokens,
                    'metadata': all_docs['metadatas'][i]
                })
                tokenized_corpus.append(tokens)
            
            # Build BM25 index
            if tokenized_corpus:
                self.bm25_index = BM25Okapi(tokenized_corpus)
                logger.info(f"BM25 index built with {len(self.agent_corpus)} agents")
            else:
                logger.warning("No agents found for BM25 index")
                self.bm25_index = None
                
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
            for i, agent_info in enumerate(self.agent_corpus):
                normalized_score = raw_scores[i] / max_score
                if normalized_score > 0:
                    bm25_scores[agent_info['agent_name']] = float(normalized_score)
            
            logger.debug(f"BM25 scores calculated for {len(bm25_scores)} agents")
            
            return bm25_scores
            
        except Exception as e:
            logger.error(f"Failed to calculate BM25 scores: {e}")
            return {}
    
    def _calculate_semantic_scores(self, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """
        Calculate semantic similarity scores using ChromaDB + LangChain.
        
        Args:
            query: The search query
            top_k: Number of top results to return
            
        Returns:
            List of dicts with agent_name, description, and semantic_score
        """
        try:
            # Use LangChain's similarity search with scores
            results_with_scores = self.vectorstore.similarity_search_with_score(
                query=query,
                k=top_k
            )
            
            semantic_results = []
            for doc, score in results_with_scores:
                # ChromaDB returns distance (lower is better), convert to similarity (higher is better)
                # Distance range is typically 0-2 for cosine, we normalize to 0-1 similarity
                similarity_score = 1 - (score / 2) if score < 2 else 0
                
                agent_name = doc.metadata.get('agent_name', 'Unknown')
                description = doc.page_content
                
                semantic_results.append({
                    'agent_name': agent_name,
                    'description': description,
                    'semantic_score': float(similarity_score),
                    'metadata': doc.metadata
                })
            
            logger.debug(f"Semantic scores calculated for {len(semantic_results)} agents")
            
            return semantic_results
            
        except Exception as e:
            logger.error(f"Failed to calculate semantic scores: {e}")
            return []
    
    def _combine_hybrid_scores(
        self,
        semantic_results: List[Dict[str, Any]],
        bm25_scores: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """
        Combine BM25 and semantic scores with weights.
        Formula: score = (BM25 × 0.25) + (Semantic × 0.75)
        
        Args:
            semantic_results: List with semantic_score
            bm25_scores: Dictionary mapping agent_name to bm25_score
        
        Returns:
            List of agents with hybrid confidence score
        """
        results = []
        
        for agent in semantic_results:
            agent_name = agent['agent_name']
            semantic_score = agent['semantic_score']
            bm25_score = bm25_scores.get(agent_name, 0.0)
            
            # Weighted hybrid score: (BM25 × 0.25) + (Semantic × 0.75)
            hybrid_score = (
                self.bm25_weight * bm25_score +
                self.semantic_weight * semantic_score
            )
            
            results.append({
                'agent_name': agent_name,
                'description': agent['description'],
                'confidence': float(hybrid_score),
                'bm25_score': float(bm25_score),
                'semantic_score': float(semantic_score),
                'metadata': agent.get('metadata', {})
            })
            
            logger.debug(f"{agent_name}: ({bm25_score:.3f}×0.25) + ({semantic_score:.3f}×0.75) = {hybrid_score:.3f}")
        
        return sorted(results, key=lambda x: x['confidence'], reverse=True)
    
    def _preprocess_query(self, query: str) -> str:
        """Clean and normalize user query before semantic search."""
        
        original_query = query
        
        # Remove URLs
        query = re.sub(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+', '', query)
        
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
            logger.info(f"Query preprocessed:")
            logger.info(f"Before: '{original_query}'")
            logger.info(f"After:  '{query}'")
        
        return query
    
    def search_agent(
        self,
        query: str,
        top_k: int = 10,
        confidence_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """
        Search for relevant agents using hybrid BM25 + semantic matching.
        
        Args:
            query: User's message/query
            top_k: Number of top results to return
            confidence_threshold: Minimum confidence score (0-1)
        
        Returns:
            List of dicts with agent_name, description, confidence, and score breakdown
        """
        try:
            logger.info("=" * 80)
            logger.info("STARTING HYBRID AGENT SEARCH (ChromaDB + LangChain)")
            logger.info(f"Original query: '{query}'")
            logger.info(f"Weights: BM25={self.bm25_weight}, Semantic={self.semantic_weight}")
            
            # Step 1: Preprocess query
            preprocessed_query = self._preprocess_query(query)
            
            # Step 2: Calculate semantic scores via ChromaDB
            logger.info("Calculating semantic similarities via ChromaDB...")
            semantic_results = self._calculate_semantic_scores(
                query=preprocessed_query,
                top_k=top_k
            )
            
            if not semantic_results:
                logger.warning("No agents found in ChromaDB")
                return []
            
            # Step 3: Calculate BM25 scores
            logger.info("Calculating BM25 scores...")
            bm25_scores = self._calculate_bm25_scores(preprocessed_query)
            
            # Step 4: Combine hybrid scores
            logger.info("Combining hybrid scores...")
            hybrid_results = self._combine_hybrid_scores(semantic_results, bm25_scores)
            
            # Step 5: Filter by threshold
            filtered_results = [
                r for r in hybrid_results if r['confidence'] >= confidence_threshold
            ][:top_k]
            
            # Step 6: Log results with clean output
            logger.info("=" * 80)
            logger.info(f"HYBRID SEARCH RESULTS: {len(filtered_results)} agents selected")
            logger.info(f"Formula: (BM25 × {self.bm25_weight}) + (Semantic × {self.semantic_weight})")
            
            for idx, result in enumerate(filtered_results, 1):
                logger.info(f"{idx}. {result['agent_name']}: ({result['bm25_score']:.3f}×{self.bm25_weight}) + ({result['semantic_score']:.3f}×{self.semantic_weight}) = {result['confidence']:.3f}")
            
            if not filtered_results:
                logger.warning(f"No agents found above threshold {confidence_threshold}")
                top_3 = [(r['agent_name'], f"{r['confidence']:.3f}") for r in hybrid_results[:3]]
                logger.info(f"Top 3 scores: {top_3}")
            
            logger.info("=" * 80)
            
            return filtered_results
            
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            logger.error(f"Error details: {str(e)}")
            return []


# ============================================================================
# LangChain LLM Reranker
# ============================================================================

class LLMReranker:
    """LLM-based reranker using LangChain for agent selection."""
    
    def __init__(self):
        """Initialize LangChain LLM for reranking."""
        self.openai_api_key = os.getenv("AZURE_OPENAI_API_KEY")
        self.openai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        self.openai_api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-02-01")
        self.model = os.getenv("AZURE_OPENAI_RERANKER_MODEL", os.getenv("AZURE_OPENAI_CHAT_MODEL", "gpt-4o-2024-11-20"))
        
        if not self.openai_api_key or not self.openai_endpoint:
            raise ValueError("Azure OpenAI API key and endpoint are required")
        
        self._initialize_llm()
        logger.info(f"LLMReranker initialized with model: {self.model}")
    
    def _initialize_llm(self):
        """Initialize LangChain Azure OpenAI LLM."""
        try:
            from langchain_openai import AzureChatOpenAI
            
            self.llm = AzureChatOpenAI(
                azure_deployment=self.model,
                openai_api_version=self.openai_api_version,
                azure_endpoint=self.openai_endpoint,
                api_key=self.openai_api_key,
                temperature=0.3,
                max_tokens=200
            )
            
            logger.info(f"LangChain LLM initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize LangChain LLM: {e}")
            raise
    
    def analyze_followup(
        self,
        current_message: str,
        conversation_history: list[dict],
        agents_registry: list[dict] | None = None,
        max_history_messages: int = 2,
        enable_query_expansion: bool = True
    ) -> FollowUpAnalysisResult:
        """
        Analyze if current message is a follow-up, expand/normalize query for semantic search,
        and infer intent (knowledge vs action). All done in a single LLM call for efficiency.
        
        Args:
            current_message: The current user message
            conversation_history: List of previous messages (dicts with 'content', 'sender', 'recipient')
            agents_registry: List of agent metadata dicts. Should include at least: {"name": str, "type": "knowledge"|"action"}
            max_history_messages: Maximum number of recent messages to consider (default: 2)
            enable_query_expansion: Whether to expand query with synonyms and related terms
        
        Returns:
            FollowUpAnalysisResult with is_followup, original_query, expanded_query, intent, and metadata
        """
        try:
            logger.info("=" * 60)
            logger.info("FOLLOW-UP ANALYSIS + QUERY EXPANSION - Starting...")
            logger.info(f"Current message: '{current_message}'")
            logger.info(f"History size: {len(conversation_history)} messages")
            
            # If no history, just do query expansion
            if not conversation_history:
                logger.info("No conversation history - performing query expansion only")
                return self._expand_query_only(
                    query=current_message,
                    enable_expansion=enable_query_expansion,
                    agents_registry=agents_registry
                )
            
            # Get recent conversation context (last N exchanges)
            recent_history = conversation_history[-max_history_messages:] if len(conversation_history) > max_history_messages else conversation_history
            logger.info(f"Using last {len(recent_history)} messages for context")
            
            # Build conversation context for LLM
            history_text = self._format_history(recent_history)
            logger.debug(f"Formatted history:\n{history_text}")

            # Provide agents registry types to LLM for intent classification.
            # Keep it compact: only name + type (and ignore any unknown keys).
            registry_for_llm: list[dict] = []
            if agents_registry:
                for a in agents_registry:
                    if not isinstance(a, dict):
                        continue
                    name = a.get("name") or a.get("agent_name")
                    agent_type = a.get("type") or a.get("agent_type")
                    if name and agent_type:
                        registry_for_llm.append({"name": str(name), "type": str(agent_type)})

            agent_registry_text = json.dumps(registry_for_llm, ensure_ascii=False)

            # Create comprehensive prompt for typo-fix + follow-up detection + query expansion + intent
            prompt = f"""You are a query normalization and intent analysis engine for an agent router.

Your output will be used for semantic search and keyword search to find relevant agents.

You MUST follow these steps EXACTLY and in this order:

Step 1 — Typo Correction (MANDATORY)
- Rewrite the current user message by fixing spelling/grammar/typos.
- Do NOT change meaning.

Step 2 — Follow-up Detection (MANDATORY)
- Decide whether the current user message depends on the conversation history.

Step 3 — Query Expansion (MANDATORY)
- Produce an `expanded_query` suitable for semantic search.
- If it IS a follow-up: enrich the expanded query with the necessary context from conversation history so the query is self-contained.
- If it is NOT a follow-up: keep it self-contained using only the corrected message.
- Expand with synonyms / alternate phrasings / key domain terms so we don't miss keyword matches.
- Keep it high-signal: do NOT add generic filler words.
- Format: a single compact search string; you may include short parenthetical synonyms, e.g. "error handling (exceptions, retries, failures)".

Step 4 — Intent Classification (MANDATORY)
- Decide whether the user intent is `knowledge` or `action`.
- Use BOTH:
    (a) the expanded_query meaning, and
    (b) the agents registry `type` values provided below (knowledge vs action).
- If the user is asking for explanations, definitions, troubleshooting guidance, how/why questions, documentation: intent=knowledge.
- If the user is asking to perform an operation, create/update something, execute a workflow, call tools/APIs, automate tasks: intent=action.

Agents Registry (name + type):
{agent_registry_text if agent_registry_text else "[]"}

Recent Conversation History:
{history_text}

Current User Message:
"{current_message}"

Respond in JSON format (no markdown, raw JSON only):
{{
    "is_followup": true or false,
    "original_query": "the exact original current message",
    "expanded_query": "enhanced query (typo-free; if follow-up, includes required context; includes synonyms/keywords)",
    "key_terms_added": ["term1", "term2"],
    "reasoning": "brief explanation of your analysis",
    "intent": "knowledge" or "action"
}}"""

            # Call Azure OpenAI
            logger.info(f"Sending analysis request to Azure OpenAI ({self.model})...")
            logger.debug(f"API Configuration: endpoint={self.openai_endpoint}, model={self.model}")
            
            
            client = AzureOpenAI(
                api_key=self.openai_api_key,
                api_version=self.openai_api_version,
                azure_endpoint=self.openai_endpoint
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at analyzing conversation context, detecting follow-up questions, and expanding queries for semantic search."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=800
            )
            
            # Parse response
            result_text = response.choices[0].message.content.strip()
            logger.info(f"Received response from Azure OpenAI")
            logger.debug(f"Raw LLM response:\n{result_text}")
            
            # Extract JSON from response (handle potential markdown wrapping)
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            result_json = json.loads(result_text)

            is_followup = bool(result_json.get("is_followup", False))
            original_query = result_json.get("original_query", current_message)
            expanded_query = result_json.get("expanded_query", current_message)
            key_terms_added = result_json.get("key_terms_added", [])
            if not isinstance(key_terms_added, list):
                key_terms_added = []
            reasoning = result_json.get("reasoning", "N/A")
            intent = result_json.get("intent", "knowledge")
            if intent not in ("knowledge", "action"):
                logger.info(f"LLM couldn't determine intent properly, defaulting to 'knowledge'")
                intent = "knowledge"
            
            logger.info("=" * 60)
            logger.info(f"ANALYSIS COMPLETE")
            logger.info(f"Is Follow-up: {is_followup}")
            logger.info(f"Reasoning: {reasoning}")

            logger.info(f"Intent: {intent}")
            logger.info(f"Expanded: '{expanded_query}'")
            logger.info("=" * 60)
            
            return FollowUpAnalysisResult(
                is_followup=is_followup,
                original_query=original_query,
                expanded_query=expanded_query,
                key_terms_added=key_terms_added,
                reasoning=reasoning,
                intent=intent
            )
            
        except Exception as e:
            logger.error(f"Follow-up analysis failed: {e}", exc_info=True)
            logger.warning(f"Falling back to original message")
            # On error, return original message without expansion
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
        agents_registry: list[dict] | None = None
    ) -> FollowUpAnalysisResult:
        """
        Expand query when there's no conversation history.
        
        Args:
            query: The user's query
            enable_expansion: Whether to expand the query
            
        Returns:
            FollowUpAnalysisResult with expanded query
        """
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

            registry_for_llm: list[dict] = []
            if agents_registry:
                for a in agents_registry:
                    if not isinstance(a, dict):
                        continue
                    name = a.get("name") or a.get("agent_name")
                    agent_type = a.get("type") or a.get("agent_type")
                    if name and agent_type:
                        registry_for_llm.append({"name": str(name), "type": str(agent_type)})

            agent_registry_text = json.dumps(registry_for_llm, ensure_ascii=False)

            prompt = f"""You are a query normalization and intent analysis engine for an agent router.

You MUST follow these steps EXACTLY and in this order:

Step 1 — Typo Correction (MANDATORY)
- Rewrite the user query by fixing spelling/grammar/typos.
- Do NOT change meaning.

Step 2 — Follow-up Detection
- There is NO conversation history in this request, so is_followup MUST be false.

Step 3 — Query Expansion
- Produce an expanded_query suitable for semantic search.
- Expand with synonyms / alternate phrasings / key domain terms so we don't miss keyword matches.
- Keep it high-signal; avoid generic filler.

Step 4 — Intent Classification
- Decide intent as `knowledge` or `action` using both the expanded_query meaning and the provided agents registry types.

Agents Registry (name + type):
{agent_registry_text if agent_registry_text else "[]"}

User Query:
"{query}"

Respond in JSON format (no markdown):
{{
    "is_followup": false,
    "original_query": "the exact original query",
    "expanded_query": "enhanced query (typo-free; includes synonyms/keywords)",
    "key_terms_added": ["term1", "term2"],
    "reasoning": "brief explanation",
    "intent": "knowledge" or "action"
}}"""

            client = AzureOpenAI(
                api_key=self.openai_api_key,
                api_version=self.openai_api_version,
                azure_endpoint=self.openai_endpoint
            )
            
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": "You are an expert at expanding queries for semantic search."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=400
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Extract JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            result_json = json.loads(result_text)
            
            expanded_query = result_json.get("expanded_query", query)
            key_terms = result_json.get("key_terms_added", [])
            if not isinstance(key_terms, list):
                key_terms = []
            reasoning = result_json.get("reasoning", "N/A")
            intent = result_json.get("intent", "knowledge")
            if intent not in ("knowledge", "action"):
                intent = "knowledge"
            
            logger.info(f"Query enhancement complete")
            logger.info(f"Original: '{query}'")
            logger.info(f"Enhanced: '{expanded_query}'")
            if key_terms:
                logger.info(f"Key terms added: {', '.join(key_terms)}")
            
            return FollowUpAnalysisResult(
                is_followup=False,
                original_query=query,
                expanded_query=expanded_query,
                key_terms_added=key_terms,
                reasoning=reasoning,
                intent=intent
            )
            
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
    
    def _format_history(self, history: list[dict]) -> str:
        """Format conversation history for LLM prompt."""
        formatted = []
        for msg in history:
            # Handle both dict and object types (UserMessage objects)
            if isinstance(msg, dict):
                sender = msg.get('sender', 'Unknown')
                recipient = msg.get('recipient', 'Unknown')
                content = msg.get('content', '')
            else:
                # Handle UserMessage or similar objects
                sender = getattr(msg, 'sender', 'Unknown')
                recipient = getattr(msg, 'recipient', 'Unknown')
                content = getattr(msg, 'content', '')
            
            if sender and sender != 'Unknown':
                formatted.append(f"[{sender}]: {content}")
            elif recipient and recipient != 'Unknown':
                formatted.append(f"[User → {recipient}]: {content}")
            else:
                formatted.append(f"{content}")
        
        return "\n".join(formatted)


class ReqAgent(BaseModel):
    name: str
    description: str
    type: str | None = None


class RequestPayload(BaseModel):
    conversation_history: Conversation
    agent_list: list[ReqAgent]
    current_message: str


class SelectedAgent(BaseModel):
    agent_name: str
    primary_agent: Optional[str] = None
    secondary_agent: Optional[str] = None
    confidence: str
    is_followup: bool
    is_parallel: bool = False
    parallel_agents: list[str] = []
    parallel_reason: str = ""


class ResponsePayload(BaseModel):
    model_config = ConfigDict(extra="allow")
    output_raw: str


class RecipientChooser:
    """RecipientChooser

    Chooses which agent should handle the next message in a conversation.
    Uses semantic search to filter agent list to top-2 matches before LLM selection.
    """

    def __init__(self, agent: RecipientChooserAgent):
        self.agent = agent
        
        # Load agent list from agents_registry database table
        self.agent_list: list[ReqAgent] = self._load_agents_from_database()
        
        # Semantic search configuration from environment variables
        self.enable_semantic_search = os.getenv("TA_ENABLE_SEMANTIC_SEARCH", "false").lower() == "true"
        self.semantic_search_top_k = int(os.getenv("TA_SEMANTIC_SEARCH_TOP_K", "2"))
        self.semantic_search_threshold = float(os.getenv("TA_SEMANTIC_SEARCH_THRESHOLD", "0.7"))
        
        # Query expansion configuration
        self.enable_query_expansion = os.getenv("TA_ENABLE_QUERY_EXPANSION", "true").lower() == "true"
        
        # Follow-up analysis configuration
        self.enable_followup_analysis = os.getenv("TA_ENABLE_FOLLOWUP_ANALYSIS", "true").lower() == "true"
        self.followup_max_history = int(os.getenv("TA_FOLLOWUP_MAX_HISTORY", "2"))
        
        # Parallel processing configuration
        self.enable_parallel_processing = os.getenv("TA_ENABLE_PARALLEL_PROCESSING", "true").lower() == "true"
        self.parallel_max_agents = int(os.getenv("TA_PARALLEL_MAX_AGENTS", "2"))
        
        # Initialize semantic search service if enabled
        self.semantic_search: Optional[ChromaDBSearchService] = None
        self.followup_analyzer: Optional[LLMReranker] = None
        
        if self.enable_semantic_search:
            try:
                # ChromaDB configuration from environment variables
                persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_agents")
                collection_name = os.getenv("CHROMA_COLLECTION_NAME", "agents_registry")
                embedding_model = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-3-small")
                bm25_weight = float(os.getenv("BM25_WEIGHT", "0.25"))
                semantic_weight = float(os.getenv("SEMANTIC_WEIGHT", "0.75"))
                
                self.semantic_search = ChromaDBSearchService(
                    persist_directory=persist_dir,
                    collection_name=collection_name,
                    embedding_model=embedding_model,
                    bm25_weight=bm25_weight,
                    semantic_weight=semantic_weight
                )
                logger.info("ChromaDB semantic search initialized successfully")
                logger.info(f"- Persist directory: {persist_dir}")
                logger.info(f"- Collection: {collection_name}")
                logger.info(f"- Top K: {self.semantic_search_top_k}")
                logger.info(f"- Threshold: {self.semantic_search_threshold}")
                logger.info(f"- BM25 Weight: {bm25_weight}, Semantic Weight: {semantic_weight}")
                
                # Initialize LLM reranker for follow-up analysis if enabled
                if self.enable_followup_analysis:
                    try:
                        self.followup_analyzer = LLMReranker()
                        logger.info("LLM reranker (follow-up analyzer) initialized successfully")
                        logger.info(f"- Max history messages: {self.followup_max_history}")
                    except Exception as e:
                        logger.error(f"Failed to initialize LLM reranker: {e}")
                        logger.warning("Continuing without follow-up analysis")
                        self.followup_analyzer = None
                        self.enable_followup_analysis = False
                
                # Log parallel processing configuration
                logger.info(f"Parallel processing: {'ENABLED' if self.enable_parallel_processing else 'DISABLED'}")
                if self.enable_parallel_processing:
                    logger.info(f"- Max parallel agents: {self.parallel_max_agents}")
                
            except Exception as e:
                logger.error(f"Failed to initialize ChromaDB semantic search: {e}")
                logger.warning("Falling back to LLM-only agent selection")
                self.semantic_search = None
                self.followup_analyzer = None
                self.enable_semantic_search = False
                self.enable_followup_analysis = False

    def _load_agents_from_database(self) -> list[ReqAgent]:
        """
        Load active agents from ChromaDB collection.
        Returns list of ReqAgent objects with name, description, and (if available) type.
        """
        try:
            
            # ChromaDB configuration from environment variables
            persist_dir = os.getenv("CHROMA_PERSIST_DIR", "./chroma_agents")
            collection_name = os.getenv("CHROMA_COLLECTION_NAME", "agents_registry")
            
            logger.info("Loading agents from ChromaDB collection...")
            logger.info(f"- Persist directory: {persist_dir}")
            logger.info(f"- Collection: {collection_name}")
            
            # Initialize ChromaDB client
            client = chromadb.PersistentClient(
                path=persist_dir,
                settings=Settings(
                    anonymized_telemetry=False,
                    allow_reset=True
                )
            )
            
            # Get collection
            collection = client.get_collection(name=collection_name)
            
            # Get all agents from collection
            all_agents = collection.get(include=["documents", "metadatas"])
            
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
                # Fallback to agent catalog if ChromaDB is empty
                return [
                    ReqAgent(
                        name=agent.name,
                        description=agent.description,
                        type=_normalize_agent_type(getattr(agent, 'type', None))
                    )
                    for agent in self.agent.agent_catalog.agents.values()
                ]
            
            return agents
            
        except Exception as e:
            logger.error(f"Failed to load agents from ChromaDB: {e}", exc_info=True)
            logger.warning("Falling back to agent catalog")
            
            # Fallback to agent catalog on error
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

    @staticmethod
    def _clean_output(output: str) -> str:
        while output[0] != "{":
            output = output[1:]
            if len(output) < 2:
                raise Exception("Invalid response")
        while output[-1] != "}":
            output = output[:-1]
            if len(output) < 2:
                raise Exception("Invalid response")
        return output
    
    async def _select_agent_with_llm_reranker(
        self,
        candidate_agents: list[dict],
        message: str,
        conv: Conversation,
        agent_scores: list[dict] | None = None,
        followup_analysis: Any | None = None
    ) -> SelectedAgent:
        """
        Use direct OpenAI LLM call as a reranker to select the best agent from candidates.
        This replaces the agent selector agent API call for efficiency.
        Respects semantic scores when available.
        
        Args:
            candidate_agents: List of ReqAgent dicts with 'name' and 'description'
            message: User's message
            conv: Conversation history
            agent_scores: Optional list of agents with semantic confidence scores
            followup_analysis: Optional FollowUpAnalysisResult from LLM (contains  is_followup, etc)
            
        Returns:
            SelectedAgent with agent_name, confidence, and is_followup
        """
        try:
            
            # Build agent descriptions with scores for LLM
            if agent_scores:
                # Build descriptions using candidate_agents data combined with scores
                agents_text = "\n".join([
                    f"- {agent['name']}: {agent['description']} [Semantic Score: {next((s.get('confidence', 0) for s in agent_scores if s['name'] == agent['name']), 0):.3f}]"
                    for agent in candidate_agents
                ])
            else:
                agents_text = "\n".join([
                    f"- {agent['name']}: {agent['description']}"
                    for agent in candidate_agents
                ])
                score_guidance = ""
            
            # Build conversation context from followup analysis if available
            conv_context = ""
            if followup_analysis:
                # Use LLM-generated summarized context from follow-up analysis
                conv_context = f"""Follow-up Analysis Result:
                        - Is Follow-up: {followup_analysis.is_followup}
                        - Query Expansion: {followup_analysis.expanded_query}"""
                logger.info(f"Using LLM-generated follow-up analysis context")
            elif conv.history:
                # Fallback: use recent conversation history if no followup analysis
                recent_msgs = conv.history[-2:]  # Last 2 messages only
                conv_context = "\n".join([
                    f"[{getattr(msg, 'sender', getattr(msg, 'name', 'Unknown'))}]: {getattr(msg, 'content', str(msg))[:100]}"
                    for msg in recent_msgs
                ])
                logger.info(f"Using raw conversation history (fallback)")
            else:
                logger.info(f"No conversation context available")
            
            # Build prompt sections based on parallel processing flag
            selection_prompt = f"""You are AgentMatcher, an intelligent assistant responsible for BOTH:
                                    1. Selecting the most suitable PRIMARY agent for the user query must select the PRIMARY agent 
                                    2.Only select the GeneralAgent for greetings (hello, hi, hey)
                                    3. Deciding whether adding ONE SECONDARY agent would meaningfully improve the response

                                    IMPORTANT CONTEXT:
                                    - You are receiving pre-analyzed context from a separate analysis LLM
                                    - The query has already been expanded with related terms
                                    - Conversation history has been summarized for you
                                    - DO NOT re-analyze the full conversation history

                                    Your responsibility is to PRODUCE AN EXECUTION PLAN, not just a classification.

                                    <agents>
                                    {agents_text}
                                    </agents>

                                    CRITICAL INSTRUCTION – AGENT NAME FORMAT:
                                    All agent names MUST include version tags exactly as shown above.
                                    Example: "BuildServiceNowAgent:0.1"
                                    DO NOT invent or alter agent names.

                                    SEMANTIC SCORES (PRIMARY SIGNAL):
                                    {chr(10).join([f" • {agent['name']}: {agent.get('confidence', 0):.3f}" for agent in agent_scores if agent['name'] in [c['name'] for c in candidate_agents]])}

                                    YOU MUST RESPECT SEMANTIC SCORES:
                                    - If the top agent has >12% score advantage, select it as PRIMARY unless the query clearly contradicts it
                                    - If scores are within 8%, treat this as ambiguity and consider secondary agent support
                                    - Override scores ONLY with strong semantic evidence

                                    PARALLEL AGENT SELECTION RULES:
                                    You may select AT MOST ONE secondary agent.
                                    Select a secondary agent ONLY IF it provides CLEAR COMPLEMENTARY VALUE.

                                    Complementary value means ONE OR MORE of the following:
                                    - Uses a different data source or system
                                    - Offers a different reasoning perspective
                                    - Validates or cross-checks the primary agent’s answer
                                    - Covers an upstream or downstream dependency
                                    - Addresses a secondary intent implied in the query

                                    DO NOT select a secondary agent if it would:
                                    - Provide redundant information
                                    - Answer the same question in a similar way
                                    - Add only marginal value

                                    CONFIDENCE-BASED BEHAVIOR:
                                    - Confidence = High → Select ONLY a primary agent
                                    - Confidence = Medium → Secondary agent MAY be selected
                                    - Confidence = Low → Prefer selecting a secondary agent if complementary value exists

                                    FOLLOW-UP HANDLING:
                                    - If this is a follow-up query, prefer the previously selected agent unless clearly inappropriate
                                    - Short replies like "yes", "ok", "tell me more" MUST be treated as follow-ups

                                    PRE-ANALYZED CONTEXT:
                                    <context>
                                    {conv_context if conv_context else "No previous conversation context."}
                                    </context>

                                    USER QUERY:
                                    <message>
                                    {message}
                                    </message>

                                    OUTPUT REQUIREMENTS:
                                    - Select agents ONLY from the <agents> list above
                                    - NEVER select GeneralAgent unless the query is ONLY a greeting (hello, hi, hey)
                                    - If GeneralAgent is not in the agents list, do NOT select it
                                    - Respond with JSON ONLY

                                    OUTPUT FORMAT (return valid JSON):
                                    primary_agent: "AgentName:0.1"
                                    secondary_agent: "AgentName:0.1 or null"
                                    confidence: "High or Medium or Low"
                                    is_followup: true or false
                                    reasoning: "Brief explanation of why this plan improves the response"
                                 """

            client = AzureOpenAI(
                api_key=os.getenv("AZURE_OPENAI_API_KEY"),
                api_version="2024-02-01",
                azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
            )
            
            # Use environment variable for model name, with fallback to actual deployment name
            reranker_model = os.getenv("AZURE_OPENAI_RERANKER_MODEL", os.getenv("AZURE_OPENAI_CHAT_MODEL", "gpt-4o-2024-11-20"))
            
            logger.info(f"Making direct LLM reranker call for agent selection (model: {reranker_model})...")
            logger.info(f"Candidates: {[a['name'] for a in candidate_agents]}")
            
            response = client.chat.completions.create(
                model=reranker_model,
                messages=[
                    {"role": "system", "content": "You are AgentMatcher, an intelligent assistant designed to analyze user queries and match them with the most suitable agent. You MUST always select one agent from the provided list."},
                    {"role": "user", "content": selection_prompt}
                ],
                temperature=0.4,
                max_tokens=200
            )
            
            result_text = response.choices[0].message.content.strip()
            logger.info(f"LLM reranker response received")
            logger.debug(f"Raw response: {result_text}")
            
            # Extract JSON from response (handle potential markdown wrapping)
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()
            
            result_json = json.loads(result_text)
            
            # Validate and ensure all agent names have version tags
            def ensure_version_tag(agent_name: str, candidate_agents: list[dict]) -> str:
                """Ensure agent name has version tag by matching with candidates."""
                # If already has version tag, return as-is
                if ":" in agent_name:
                    return agent_name
                
                # Find matching candidate with version tag
                base_name = agent_name.split(":")[0]
                for candidate in candidate_agents:
                    if candidate["name"].split(":")[0] == base_name:
                        logger.info(f"Enriched agent name: {agent_name} → {candidate['name']}")
                        return candidate["name"]
                
                logger.warning(f"Could not find versioned name for '{agent_name}', using as-is")
                return agent_name
         
            parallel_agents_list = result_json.get("parallel_agents", [])
            enriched_parallel_agents = []
            for parallel_agent_name in parallel_agents_list:
                enriched_name = ensure_version_tag(parallel_agent_name, candidate_agents)
                enriched_parallel_agents.append(enriched_name)
            
            primary_agent_name = ensure_version_tag(result_json["primary_agent"], candidate_agents)
            secondary_agent_name = ensure_version_tag(result_json["secondary_agent"], candidate_agents) if result_json.get("secondary_agent") else None
            
            selected_agent = SelectedAgent(
                agent_name=primary_agent_name,
                primary_agent=primary_agent_name,
                secondary_agent=secondary_agent_name,
                confidence=result_json["confidence"],
                is_followup=result_json.get("is_followup", False),
                is_parallel=False,  # Will be set by Stage 2 if needed
                parallel_agents=[],
                parallel_reason=""
            )
            
            
            return selected_agent
            
        except Exception as e:
            logger.error(f"LLM reranker failed: {e}", exc_info=True)
            # Fallback to first agent if reranker fails
            logger.warning(f"Falling back to first candidate: {candidate_agents[0]['name']}")
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

    async def choose_recipient(self, message: str, conv: Conversation) -> SelectedAgent:
        """Chooses the recipient

        Args:
            message (str): The current message from the client
            conv (Conversation): The conversation history, so far
        Returns:
            The name of the agent that should handle the message
        """
        # Start with full agent list
        filtered_agent_list = self.agent_list
        
        # Try semantic search first to filter to top-2 agentscompos
        if self.enable_semantic_search and self.semantic_search:
            try:
                logger.info("=" * 80)
                logger.info("SEMANTIC SEARCH - Agent Filtering")
                
                # Perform follow-up analysis if enabled (query expansion)
                search_query = message
                followup_result = None
                if self.enable_followup_analysis and self.followup_analyzer:
                    try:
                        agents_registry_for_intent = [
                            {"name": agent.name, "type": agent.type}
                            for agent in self.agent_list
                            if agent.type
                        ]
                        followup_result = self.followup_analyzer.analyze_followup(
                            current_message=message,
                            conversation_history=[
                                {'content': getattr(msg, 'content', str(msg)), 
                                 'sender': getattr(msg, 'sender', 'Unknown'),
                                 'recipient': getattr(msg, 'recipient', 'Unknown')}
                                for msg in conv.history
                            ] if conv.history else [],
                            agents_registry=agents_registry_for_intent,
                            max_history_messages=self.followup_max_history,
                            enable_query_expansion=self.enable_query_expansion
                        )
                        search_query = followup_result.expanded_query
                        logger.info(f"Query: '{message}' → '{search_query}'")
                        logger.info(f"Is Follow-up: {followup_result.is_followup}")
                    except Exception as followup_error:
                        logger.warning(f"Follow-up analysis failed: {followup_error}")
                        search_query = message
                        followup_result = None
                
                # Search for ALL agents to get full confidence scores (not just top-k)
                all_results = self.semantic_search.search_agent(
                    query=search_query,
                    top_k=10,  # Get all agents
                    confidence_threshold=0.0  # No threshold filtering yet
                )
                
                if all_results: 
                    # sending top 5 to the reranker LLM    
                    search_results = all_results[:5]
                    
                    # Standard single-agent selection with LLM reranker
                    if search_results:
                        logger.info(f"Candidates from semantic search:")
                        for result in search_results:
                            # bm25_c = result['bm25_score'] * self.semantic_search.bm25_weight
                            # sem_c = result['semantic_score'] * self.semantic_search.semantic_weight
                            logger.info(f"{result['agent_name']}: ({result['bm25_score']:.3f}×0.25) + ({result['semantic_score']:.3f}×0.75) = {result['confidence']:.3f}")
                        
                        # Filter out GeneralAgent unless query is a pure greeting
                        greeting_keywords = ['hello', 'hi', 'hey', 'good morning', 'good afternoon', 'good evening']
                        message_lower = message.lower().strip()
                        is_pure_greeting = any(message_lower == kw or message_lower.startswith(kw + ' ') or message_lower.startswith(kw + ',') for kw in greeting_keywords) and len(message.split()) <= 5
                        
                        if not is_pure_greeting:
                            search_results = [r for r in search_results if 'GeneralAgent' not in r['agent_name']]
                        
                        logger.info(f"Using LLM reranker for final selection...")
                        
                        # Prepare candidate list for reranker
                        reranker_candidates = [
                            {'name': result['agent_name'], 'description': result['description']}
                            for result in search_results
                        ]
                        
                        # Prepare scores list for guidance
                        agent_scores_list = [
                            {'name': result['agent_name'], 'confidence': result['confidence']}
                            for result in search_results
                        ]
                        
                        selected_agent = await self._select_agent_with_llm_reranker(
                            candidate_agents=reranker_candidates,
                            message=message,
                            conv=conv,
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
        
        # Use LLM reranker for agent selection (replaces agent selector agent API call): 
        # print statements TBD
        print("=" * 80, flush=True)
        print("LLM RERANKER - Selecting best agent from candidates...", flush=True)
        print(f"Agents in selection pool: {len(filtered_agent_list)}", flush=True)
        print("=" * 80, flush=True)
        
        logger.info("=" * 80)
        logger.info("LLM RERANKER - Agent Selection")
        logger.info(f"Candidate count: {len(filtered_agent_list)}")
        
        # Perform follow-up analysis if not already done by semantic search
        followup_result = None
        if self.enable_followup_analysis and self.followup_analyzer:
            try:
                followup_result = self.followup_analyzer.analyze_followup(
                    current_message=message,
                    conversation_history=[
                        {'content': getattr(msg, 'content', str(msg)), 
                         'sender': getattr(msg, 'sender', 'Unknown'),
                         'recipient': getattr(msg, 'recipient', 'Unknown')}
                        for msg in conv.history
                    ] if conv.history else [],
                    max_history_messages=self.followup_max_history,
                    enable_query_expansion=self.enable_query_expansion
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
        
        # Use direct LLM call as reranker with followup analysis
        selected_agent = await self._select_agent_with_llm_reranker(
            candidate_agents=reranker_candidates,
            message=message,
            conv=conv,
            followup_analysis=followup_result
        )
        
        return selected_agent
