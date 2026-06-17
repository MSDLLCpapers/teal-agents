"""
Models for recipient/agent selection.

This module contains all data models related to the agent selection process,
including follow-up analysis, agent representations, and selection results.
"""

from typing import Optional, Literal, Any
from pydantic import BaseModel, ConfigDict, Field


class FollowUpAnalysisResult(BaseModel):
    """Result from follow-up analysis with query expansion."""
    is_followup: bool
    original_query: str
    expanded_query: str
    key_terms_added: list[str] = Field(default_factory=list)
    reasoning: str = ""
    intent: Literal["knowledge", "action"] = "knowledge"


class ReqAgent(BaseModel):
    """Agent representation for selection."""
    name: str
    description: str
    type: str | None = None


class SelectedAgent(BaseModel):
    """Result of agent selection process."""
    agent_name: str
    primary_agent: Optional[str] = None
    secondary_agent: Optional[str] = None
    confidence: str
    is_followup: bool
    is_parallel: bool = False
    parallel_agents: list[str] = Field(default_factory=list)
    parallel_reason: str = ""


class RequestPayload(BaseModel):
    """Payload for agent selection request.
    
    Note: conversation_history uses Any type to avoid circular import
    with the external Conversation model.
    """
    conversation_history: Any  # External Conversation type
    agent_list: list[ReqAgent]
    current_message: str


class ResponsePayload(BaseModel):
    """Payload for agent selection response."""
    model_config = ConfigDict(extra="allow")
    output_raw: str


class AgentCandidate(BaseModel):
    """Agent candidate for LLM reranker."""
    name: str
    description: str


class AgentScore(BaseModel):
    """Agent with confidence score from semantic search."""
    name: str
    confidence: float


class LLMRerankerInput(BaseModel):
    """Input for LLM reranker."""
    candidate_agents: list[AgentCandidate]
    message: str
    agent_scores: list[AgentScore] = Field(default_factory=list)
    followup_analysis: Optional[FollowUpAnalysisResult] = None
    conversation_context: str = ""
