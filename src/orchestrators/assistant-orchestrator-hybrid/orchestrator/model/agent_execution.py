"""
Models for agent execution.

This module contains data models for agent execution results,
parallel execution, and response aggregation.
"""

from typing import Optional, Any
from pydantic import BaseModel, Field


class AgentExecutionResult(BaseModel):
    """Result from single agent execution."""
    success: bool
    agent_name: str
    response: Optional[str] = None
    raw_response: Optional[dict[str, Any]] = None
    error: Optional[str] = None
    duration: float = 0.0


class ParallelExecutionResult(BaseModel):
    """Result from parallel agent execution."""
    success: bool
    parallel_mode: bool = True
    results: dict[str, AgentExecutionResult] = Field(default_factory=dict)
    duration: float = 0.0
    total_agents: int = 0
    successful_agents: int = 0
    failed_agents: int = 0
    error: Optional[str] = None


class AggregatedResponse(BaseModel):
    """Synthesized response from multiple agents."""
    success: bool = True
    synthesized_response: str = ""  # Main response field (backward compatible)
    content: Optional[str] = None  # Alias for synthesized_response
    source_agents: list[str] = Field(default_factory=list)
    successful_count: int = 0
    failed_count: int = 0
    synthesis_duration: float = 0.0
    total_duration: float = 0.0
    fallback_used: bool = False
    error: Optional[str] = None
    
    def __init__(self, **data):
        """Initialize with backward compatibility."""
        # Support both 'content' and 'synthesized_response'
        if 'content' in data and 'synthesized_response' not in data:
            data['synthesized_response'] = data['content']
        elif 'synthesized_response' in data and 'content' not in data:
            data['content'] = data['synthesized_response']
        super().__init__(**data)


class AgentInvocationContext(BaseModel):
    """Context for agent invocation."""
    conversation_id: str
    user_id: str
    message: str
    authorization: Optional[str] = None
    image_data: Optional[str] = None


class StreamingChunk(BaseModel):
    """Chunk of streaming response from agent."""
    content: str
    agent_name: str
    is_final: bool = False
    extra_data: Optional[dict[str, Any]] = None
