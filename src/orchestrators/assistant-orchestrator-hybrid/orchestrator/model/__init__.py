"""
Model package for orchestrator.

This package contains all data models used across the orchestrator,
organized by domain.
"""

# Re-export from submodules
from .recipient_chooser import (
    FollowUpAnalysisResult,
    ReqAgent,
    SelectedAgent,
    RequestPayload,
    ResponsePayload,
    AgentCandidate,
    AgentScore,
    LLMRerankerInput,
)

from .search import (
    SemanticSearchResult,
    AgentSearchResult,
    HybridSearchResponse,
    AgentCorpusEntry,
)

from .agent_execution import (
    AgentExecutionResult,
    ParallelExecutionResult,
    AggregatedResponse,
    AgentInvocationContext,
    StreamingChunk,
)

from .conversation import (
    ContextType,
    ContextItem,
    UserMessage,
    AgentMessage,
    Conversation,
    SseMessage,
)

__all__ = [
    # Recipient Chooser Models
    "FollowUpAnalysisResult",
    "ReqAgent",
    "SelectedAgent",
    "RequestPayload",
    "ResponsePayload",
    "AgentCandidate",
    "AgentScore",
    "LLMRerankerInput",
    # Search Models
    "SemanticSearchResult",
    "AgentSearchResult",
    "HybridSearchResponse",
    "AgentCorpusEntry",
    # Agent Execution Models
    "AgentExecutionResult",
    "ParallelExecutionResult",
    "AggregatedResponse",
    "AgentInvocationContext",
    "StreamingChunk",
    # Conversation Models
    "ContextType",
    "ContextItem",
    "UserMessage",
    "AgentMessage",
    "Conversation",
    "SseMessage",
]
