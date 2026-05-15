"""
Prompts for query analysis and follow-up detection.

This module contains system prompts and prompt builders for:
- Follow-up detection
- Query expansion
- Intent classification
"""

import json
from typing import Optional


QUERY_ANALYSIS_SYSTEM_PROMPT = """You are an expert at analyzing conversation context, detecting follow-up questions, and expanding queries for semantic search."""


QUERY_EXPANSION_SYSTEM_PROMPT = """You are an expert at expanding queries for semantic search."""


def build_followup_analysis_prompt(
    current_message: str,
    history_text: str,
    agent_registry_text: str = "[]"
) -> str:
    """
    Build the prompt for follow-up analysis with query expansion.
    
    Args:
        current_message: The current user message
        history_text: Formatted conversation history
        agent_registry_text: JSON string of agent registry (name + type)
        
    Returns:
        Complete prompt for LLM
    """
    return f"""You are a query normalization and intent analysis engine for an agent router.

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
{agent_registry_text}

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


def build_query_expansion_prompt(
    query: str,
    agent_registry_text: str = "[]"
) -> str:
    """
    Build the prompt for query expansion (when there's no conversation history).
    
    Args:
        query: The user's query
        agent_registry_text: JSON string of agent registry (name + type)
        
    Returns:
        Complete prompt for LLM
    """
    return f"""You are a query normalization and intent analysis engine for an agent router.

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
{agent_registry_text}

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


def format_conversation_history(history: list[dict]) -> str:
    """
    Format conversation history for LLM prompt.
    
    Args:
        history: List of message dicts with 'content', 'sender', 'recipient' keys
        
    Returns:
        Formatted string for prompt
    """
    formatted = []
    for msg in history:
        if isinstance(msg, dict):
            sender = msg.get('sender', 'Unknown')
            recipient = msg.get('recipient', 'Unknown')
            content = msg.get('content', '')
        else:
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


def build_agent_registry_text(agents_registry: Optional[list[dict]]) -> str:
    """
    Build JSON text of agent registry for LLM prompt.
    
    Args:
        agents_registry: List of agent dicts with 'name' and 'type' keys
        
    Returns:
        JSON string of registry
    """
    registry_for_llm: list[dict] = []
    if agents_registry:
        for a in agents_registry:
            if not isinstance(a, dict):
                continue
            name = a.get("name") or a.get("agent_name")
            agent_type = a.get("type") or a.get("agent_type")
            if name and agent_type:
                registry_for_llm.append({"name": str(name), "type": str(agent_type)})
    
    return json.dumps(registry_for_llm, ensure_ascii=False)
