"""
Models for hybrid search service.

This module contains data models for hybrid search results combining
BM25 lexical matching and semantic similarity.
"""

from typing import Any
from pydantic import BaseModel, Field


class SemanticSearchResult(BaseModel):
    """Result from semantic similarity search."""
    agent_name: str
    description: str
    semantic_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentSearchResult(BaseModel):
    """Result from hybrid agent search with combined BM25 + semantic scores."""
    agent_name: str
    description: str
    confidence: float
    bm25_score: float
    semantic_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)
    
    def to_candidate(self) -> dict[str, str]:
        """Convert to candidate dict format for LLM reranker.
        
        Returns:
            Dict with 'name' and 'description' keys
        """
        return {
            "name": self.agent_name,
            "description": self.description
        }
    
    def to_score(self) -> dict[str, Any]:
        """Convert to score dict format for LLM reranker guidance.
        
        Returns:
            Dict with 'name' and 'confidence' keys
        """
        return {
            "name": self.agent_name,
            "confidence": self.confidence
        }


class HybridSearchResponse(BaseModel):
    """Aggregated response from hybrid search."""
    results: list[AgentSearchResult]
    query_original: str
    query_preprocessed: str
    total_agents_searched: int
    bm25_weight: float
    semantic_weight: float


class AgentCorpusEntry(BaseModel):
    """Entry in the BM25 agent corpus."""
    agent_name: str
    description: str
    tokens: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)
