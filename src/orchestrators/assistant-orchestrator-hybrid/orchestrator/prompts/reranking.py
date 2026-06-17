"""
Prompts for response reranking and synthesis.

This module contains system prompts and prompt builders for:
- Response aggregation from multiple agents
- Response synthesis
"""


RESPONSE_SYNTHESIS_SYSTEM_PROMPT = """You are an expert at synthesizing information from multiple specialized agents and creating unified, coherent responses."""


def build_response_synthesis_prompt(
    responses_text: str,
    user_message: str = "Unknown query"
) -> str:
    """
    Build the prompt for synthesizing responses from multiple agents.
    
    Args:
        responses_text: Formatted responses from multiple agents
        user_message: The original user query
        
    Returns:
        Complete prompt for LLM
    """
    return f"""You are an expert at synthesizing information from multiple specialized agents.

User Query: "{user_message}"

Responses from different agents:
{responses_text}

Your task:
1. Synthesize all responses into a cohesive, comprehensive answer
2. For each agent's contribution, clearly label it with the agent name
3. Highlight any contradictions or complementary information
4. Organize information logically by topic and theme, not just by agent
5. Remove redundancy while preserving unique insights
6. Create a unified narrative that flows well

Format:
- Start with a brief summary of the key findings
- Then organize by topic with agent attributions in brackets like [AgentName]
- End with any important notes or caveats

Make the response professional, coherent, and directly address the user's query."""


def format_parallel_responses(
    results: dict,
    include_errors: bool = True
) -> str:
    """
    Format parallel agent responses for synthesis.
    
    Args:
        results: Dictionary of agent results with 'success', 'response', 'error' keys
        include_errors: Whether to include failed agent errors
        
    Returns:
        Formatted string of all responses
    """
    responses_text = ""
    
    for agent_name, result in results.items():
        if result.get("success"):
            response_text = result.get("response", "No response")
            responses_text += f"\n## {agent_name}\n{response_text}\n"
        elif include_errors:
            error_msg = result.get("error", "Unknown error")
            responses_text += f"\n## {agent_name} (FAILED)\nError: {error_msg}\n"
    
    return responses_text


def build_fallback_response(results: dict) -> str:
    """
    Build a simple fallback response when LLM synthesis fails.
    
    Args:
        results: Dictionary of agent results
        
    Returns:
        Simple concatenated response
    """
    fallback_response = "**Parallel Agent Responses:**\n"
    
    for agent_name, result in results.items():
        if result.get("success"):
            fallback_response += f"\n## {agent_name}\n{result.get('response', 'No response')}\n"
        else:
            fallback_response += f"\n## {agent_name} (Failed)\nError: {result.get('error', 'Unknown error')}\n"
    
    return fallback_response
