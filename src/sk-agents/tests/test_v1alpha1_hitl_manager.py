import pytest
from semantic_kernel.contents.function_call_content import FunctionCallContent

from sk_agents.tealagents.v1alpha1.hitl_manager import (
    HitlInterventionRequired,
    check_for_intervention,
)


@pytest.mark.parametrize(
    "plugin_name,function_name,expected",
    [
        ("sensitive_plugin", "delete_user_data", True),
        ("finance_plugin", "initiate_transfer", True),
        ("admin_tools", "shutdown_service", True),
        ("utility_plugin", "ShellCommand", True),
        ("safe_plugin", "get_status", False),
        ("finance_plugin", "get_balance", False),
    ],
)
def test_check_for_intervention(plugin_name, function_name, expected):
    tool_call = FunctionCallContent(plugin_name=plugin_name, function_name=function_name)
    assert check_for_intervention(tool_call) == expected


def test_hitl_intervention_required_exception_single():
    plugin_name = "sensitive_plugin"
    function_name = "delete_user_data"
    fc = FunctionCallContent(plugin_name=plugin_name, function_name=function_name)

    with pytest.raises(HitlInterventionRequired) as exc_info:
        raise HitlInterventionRequired([fc])

    exc = exc_info.value
    assert str(exc) == f"HITL intervention required for {plugin_name}.{function_name}"
    assert exc.plugin_name == plugin_name
    assert exc.function_name == function_name
    assert fc in exc.function_calls


def test_hitl_intervention_required_exception_multiple():
    fc1 = FunctionCallContent(plugin_name="sensitive_plugin", function_name="delete_user_data")
    fc2 = FunctionCallContent(plugin_name="finance_plugin", function_name="initiate_transfer")
    exc = HitlInterventionRequired([fc1, fc2])

    assert fc1 in exc.function_calls
    assert fc2 in exc.function_calls
