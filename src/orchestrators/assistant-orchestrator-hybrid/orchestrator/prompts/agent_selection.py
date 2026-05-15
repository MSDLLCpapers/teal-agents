"""
Prompts for agent selection and matching.

This module contains system prompts and prompt builders for:
- Agent matching/selection
- Primary and secondary agent selection
- LLM reranking
"""

from typing import Optional


AGENT_SELECTION_SYSTEM_PROMPT = """You are AgentMatcher, an intelligent assistant designed to analyze user queries and match them with the most suitable agent. You MUST always select one agent from the provided list."""


def build_agent_selection_prompt(
    agents_text: str,
    semantic_scores_text: str,
    conv_context: str,
    message: str
) -> str:
    """
    Build the prompt for agent selection with LLM reranker.
    
    Args:
        agents_text: Formatted list of agents with descriptions
        semantic_scores_text: Formatted semantic scores for each agent
        conv_context: Conversation context (from follow-up analysis or raw history)
        message: The user's message
        
    Returns:
        Complete prompt for LLM
    """
    return f"""You are AgentMatcher, an intelligent assistant responsible for BOTH:
1. Selecting the most suitable PRIMARY agent for the user query must select the PRIMARY agent 
2. Only select the GeneralAgent for greetings (hello, hi, hey)
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
{semantic_scores_text}

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
- Validates or cross-checks the primary agent's answer
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


def build_agents_text(
    candidate_agents: list[dict],
    agent_scores: Optional[list[dict]] = None
) -> str:
    """
    Build formatted agents text for LLM prompt.
    
    Args:
        candidate_agents: List of agent dicts with 'name' and 'description'
        agent_scores: Optional list of agents with 'confidence' scores
        
    Returns:
        Formatted string of agents with descriptions and scores
    """
    if agent_scores:
        return "\n".join([
            f"- {agent['name']}: {agent['description']} [Semantic Score: {next((s.get('confidence', 0) for s in agent_scores if s['name'] == agent['name']), 0):.3f}]"
            for agent in candidate_agents
        ])
    else:
        return "\n".join([
            f"- {agent['name']}: {agent['description']}"
            for agent in candidate_agents
        ])


def build_semantic_scores_text(
    agent_scores: list[dict],
    candidate_agents: list[dict]
) -> str:
    """
    Build formatted semantic scores text for LLM prompt.
    
    Args:
        agent_scores: List of agents with 'name' and 'confidence' scores
        candidate_agents: List of candidate agent dicts
        
    Returns:
        Formatted string of semantic scores
    """
    candidate_names = [c['name'] for c in candidate_agents]
    return chr(10).join([
        f" • {agent['name']}: {agent.get('confidence', 0):.3f}"
        for agent in agent_scores
        if agent['name'] in candidate_names
    ])


def build_conversation_context(
    followup_analysis: Optional[object] = None,
    conversation_history: Optional[list] = None
) -> str:
    """
    Build conversation context for agent selection.
    
    Args:
        followup_analysis: FollowUpAnalysisResult object (if available)
        conversation_history: Raw conversation history (fallback)
        
    Returns:
        Formatted context string
    """
    if followup_analysis:
        return f"""Follow-up Analysis Result:
- Is Follow-up: {followup_analysis.is_followup}
- Query Expansion: {followup_analysis.expanded_query}"""
    
    if conversation_history:
        recent_msgs = conversation_history[-2:]
        return "\n".join([
            f"[{getattr(msg, 'sender', getattr(msg, 'name', 'Unknown'))}]: {getattr(msg, 'content', str(msg))[:100]}"
            for msg in recent_msgs
        ])
    
    return ""
