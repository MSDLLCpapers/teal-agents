from semantic_kernel.contents.function_call_content import FunctionCallContent


def check_for_intervention(tool_call: FunctionCallContent) -> bool:
    """
    Placeholder for HITL logic. In the future, this will check
    if the tool call requires user consent based on configured policies.

    Returns False for now, allowing all calls to proceed without interruption.
    """

    # TODO: Implement actual policy checks for high-risk tools
    print(
        f"HITL Check: Intercepted call to {tool_call.plugin_name}."
        f"{tool_call.function_name}. Allowing to proceed."
    )
    return False
