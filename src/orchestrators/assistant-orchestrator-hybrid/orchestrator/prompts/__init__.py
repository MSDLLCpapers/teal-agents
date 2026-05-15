"""Prompts package for LLM interactions."""

from .query_analysis import (
    QUERY_ANALYSIS_SYSTEM_PROMPT,
    build_followup_analysis_prompt,
    build_query_expansion_prompt,
)
from .agent_selection import (
    AGENT_SELECTION_SYSTEM_PROMPT,
    build_agent_selection_prompt,
)
from .reranking import (
    RESPONSE_SYNTHESIS_SYSTEM_PROMPT,
    build_response_synthesis_prompt,
)

__all__ = [
    # Query Analysis
    "QUERY_ANALYSIS_SYSTEM_PROMPT",
    "build_followup_analysis_prompt",
    "build_query_expansion_prompt",
    # Agent Selection
    "AGENT_SELECTION_SYSTEM_PROMPT",
    "build_agent_selection_prompt",
    # Reranking
    "RESPONSE_SYNTHESIS_SYSTEM_PROMPT",
    "build_response_synthesis_prompt",
]
