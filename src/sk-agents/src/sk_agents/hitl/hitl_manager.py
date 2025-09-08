from semantic_kernel.contents.function_call_content import (
    FunctionCallContent
)
from sk_agents.plugincatalog import plugin_catalog_factory


def check_for_intervention(tool_call: FunctionCallContent) -> bool:
    """
    Checks the plugin catalog to determine if a tool call requires
    Human-in-the-Loop intervention.
    """
    catalog = plugin_catalog_factory.get_instance()
    if not catalog:
        # Fallback if catalog is not configured
        return False

    tool_id = f"{tool_call.plugin_name}-{tool_call.function_name}"
    tool = catalog.get_tool(tool_id)

    if tool:
        print(
            f"HITL Check: Intercepted call to {tool_id}."
            f"Requires HITL: {tool.governance.requires_hitl}"
        )
        return tool.governance.requires_hitl

    # Default to no intervention if tool is not in the catalog
    return False


# Custom exception for HITL intervention
class HitlInterventionRequired(Exception):
    """
    Exception raised when a tool call
    requires human-in-the-loop intervention.
    """

    def __init__(self, function_calls: list[FunctionCallContent]):
        self.function_calls = function_calls
        if function_calls:
            self.plugin_name = function_calls[0].plugin_name
            self.function_name = function_calls[0].function_name
            message = (
                f"HITL intervention required for "
                f"{self.plugin_name}.{self.function_name}"
            )

        else:
            message = "HITL intervention required"
        super().__init__(message)
