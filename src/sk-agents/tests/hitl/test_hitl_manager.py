from unittest.mock import Mock, patch

import pytest
from semantic_kernel.contents.function_call_content import FunctionCallContent

from sk_agents.hitl.hitl_manager import (
    HitlInterventionRequired,
    check_for_intervention,
)
from sk_agents.plugin_catalog.models import Governance, PluginTool


@pytest.fixture
def mock_plugin_catalog():
    """Create a mock plugin catalog with test data."""
    catalog = Mock()

    # Define test tools that require HITL intervention
    sensitive_tool = PluginTool(
        tool_id="sensitive_plugin-delete_user_data",
        name="Delete User Data",
        description="Deletes sensitive user data",
        governance=Governance(requires_hitl=True, cost="high", data_sensitivity="sensitive"),
    )

    finance_tool = PluginTool(
        tool_id="finance_plugin-initiate_transfer",
        name="Initiate Transfer",
        description="Initiates financial transfer",
        governance=Governance(requires_hitl=True, cost="high", data_sensitivity="confidential"),
    )

    admin_tool = PluginTool(
        tool_id="admin_tools-shutdown_service",
        name="Shutdown Service",
        description="Shuts down critical service",
        governance=Governance(requires_hitl=True, cost="high", data_sensitivity="proprietary"),
    )

    shell_tool = PluginTool(
        tool_id="utility_plugin-ShellCommand",
        name="Shell Command",
        description="Executes shell commands",
        governance=Governance(requires_hitl=True, cost="medium", data_sensitivity="proprietary"),
    )

    # Define a safe tool that doesn't require HITL
    balance_tool = PluginTool(
        tool_id="finance_plugin-get_balance",
        name="Get Balance",
        description="Gets account balance",
        governance=Governance(requires_hitl=False, cost="low", data_sensitivity="public"),
    )

    # Configure catalog mock to return tools
    def get_tool_side_effect(tool_id):
        tools_map = {
            "sensitive_plugin-delete_user_data": sensitive_tool,
            "finance_plugin-initiate_transfer": finance_tool,
            "admin_tools-shutdown_service": admin_tool,
            "utility_plugin-ShellCommand": shell_tool,
            "finance_plugin-get_balance": balance_tool,
        }
        return tools_map.get(tool_id, None)

    catalog.get_tool.side_effect = get_tool_side_effect
    return catalog


@pytest.mark.parametrize(
    "plugin_name,function_name,expected",
    [
        ("sensitive_plugin", "delete_user_data", True),
        ("finance_plugin", "initiate_transfer", True),
        ("admin_tools", "shutdown_service", True),
        ("utility_plugin", "ShellCommand", True),
        ("safe_plugin", "get_status", False),  # unregistered
        ("finance_plugin", "get_balance", False),
    ],
)
def test_check_for_intervention(plugin_name, function_name, expected, mock_plugin_catalog):
    tool_call = FunctionCallContent(plugin_name=plugin_name, function_name=function_name)

    # Mock the PluginCatalogFactory to return our test catalog
    with patch("sk_agents.hitl.hitl_manager.PluginCatalogFactory") as mock_factory:
        mock_factory.return_value.get_catalog.return_value = mock_plugin_catalog

        result = check_for_intervention(tool_call)
        assert result == expected


def test_check_for_intervention_no_catalog():
    """Test check_for_intervention when catalog is None (covers line 17)."""
    tool_call = FunctionCallContent(plugin_name="test_plugin", function_name="test_function")

    # Mock the PluginCatalogFactory to return None catalog
    with patch("sk_agents.hitl.hitl_manager.PluginCatalogFactory") as mock_factory:
        mock_factory.return_value.get_catalog.return_value = None

        result = check_for_intervention(tool_call)
        assert result is False


def test_check_for_intervention_catalog_returns_false():
    """Test check_for_intervention when catalog.get_catalog() returns a falsy value."""
    tool_call = FunctionCallContent(plugin_name="test_plugin", function_name="test_function")

    # Mock the PluginCatalogFactory to return empty catalog
    with patch("sk_agents.hitl.hitl_manager.PluginCatalogFactory") as mock_factory:
        mock_factory.return_value.get_catalog.return_value = False

        result = check_for_intervention(tool_call)
        assert result is False


def test_hitl_intervention_required_exception_single():
    plugin_name = "sensitive_plugin"
    function_name = "delete_user_data"
    fc = FunctionCallContent(plugin_name=plugin_name, function_name=function_name)

    with pytest.raises(HitlInterventionRequired) as exc_info:
        raise HitlInterventionRequired([fc])

    exc = exc_info.value
    assert str(exc) == (f"HITL intervention required for {plugin_name}.{function_name}")
    assert exc.plugin_name == plugin_name
    assert exc.function_name == function_name
    assert fc in exc.function_calls


def test_hitl_intervention_required_exception_multiple():
    fc1 = FunctionCallContent(plugin_name="sensitive_plugin", function_name="delete_user_data")
    fc2 = FunctionCallContent(plugin_name="finance_plugin", function_name="initiate_transfer")
    exc = HitlInterventionRequired([fc1, fc2])

    assert fc1 in exc.function_calls
    assert fc2 in exc.function_calls


def test_hitl_intervention_required_exception_empty_list():
    """Test HitlInterventionRequired with empty function_calls list (covers line 48)."""
    exc = HitlInterventionRequired([])

    # Should use the fallback message
    assert str(exc) == "HITL intervention required"
    assert exc.function_calls == []
    # These attributes should not exist when function_calls is empty
    assert not hasattr(exc, "plugin_name") or exc.plugin_name is None
    assert not hasattr(exc, "function_name") or exc.function_name is None
