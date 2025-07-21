import os
import tempfile
from unittest.mock import patch

import pytest

from sk_agents.ska_types import IntermediateTaskResponse, InvokeResponse, PartialResponse
from sk_agents.utils import (
    docstring_parameter,
    get_sse_event_for_response,
    initialize_plugin_loader,
)


class DummyAppConfig:
    def __init__(self, initial=None):
        self.props = initial or {}

    def get(self, key):
        return self.props.get(key)


@pytest.fixture
def dummy_response_objects():
    dummy_token_usage = {
        "total_tokens": 10,
        "prompt_tokens": 5,
        "completion_tokens": 5,
    }

    invoke_resp = InvokeResponse(
        response_id="3",
        output="done",
        task_no=3,
        task_name="Final Task",
        response=None,
        token_usage=dummy_token_usage,
    )

    intermediate = IntermediateTaskResponse(
        response_id="1",
        output="step 1",
        task_no=1,
        task_name="Test Task",
        response=invoke_resp,
    )

    partial = PartialResponse(
        response_id="2",
        output="partial",
        task_no=2,
        task_name="Partial Task",
        response=invoke_resp,
        output_partial="partial output here",
    )

    return intermediate, partial, invoke_resp


def test_initialize_plugin_loader_with_defined_plugin():
    config = DummyAppConfig({"TA_PLUGIN_MODULE": "some.plugin"})
    with patch("sk_agents.utils.get_plugin_loader") as mock_loader:
        initialize_plugin_loader("fake_path", config)
        mock_loader.assert_called_once_with("some.plugin")


def test_initialize_plugin_loader_with_custom_plugins_file():
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_path = os.path.join(tmpdir, "custom_plugins.py")
        with open(plugin_path, "w") as f:
            f.write("# plugin stub")

        config = DummyAppConfig()
        with patch("sk_agents.utils.get_plugin_loader") as mock_loader:
            initialize_plugin_loader(tmpdir, config)
            assert config.props["TA_PLUGIN_MODULE"] == plugin_path
            mock_loader.assert_called_once_with(plugin_path)


def test_initialize_plugin_loader_raises_exception():
    config = DummyAppConfig({"TA_PLUGIN_MODULE": "bad.plugin"})
    with patch("sk_agents.utils.get_plugin_loader", side_effect=RuntimeError("fail")):
        with pytest.raises(RuntimeError, match="fail"):
            initialize_plugin_loader("fake_path", config)


def test_get_sse_event_for_response_unknown_type():
    class WeirdResponse:
        def __str__(self):
            return "weird"

    event = get_sse_event_for_response(WeirdResponse())
    assert "unknown" in event
    assert "weird" in event


def test_docstring_parameter_on_function():
    @docstring_parameter("arg1", "arg2")
    def example():
        """This is a doc with {} and {}."""
        pass

    assert example.__doc__ == "This is a doc with arg1 and arg2."


def test_docstring_parameter_on_class():
    @docstring_parameter("value")
    class Example:
        """This docstring includes {}."""

    assert Example.__doc__ == "This docstring includes value."


def test_get_sse_event_known_responses(dummy_response_objects):
    expected_events = [
        "intermediate-task-response",
        "partial-response",
        "final-response",
    ]

    for response, expected_event in zip(dummy_response_objects, expected_events, strict=False):
        result = get_sse_event_for_response(response)
        assert result.startswith(f"event: {expected_event}")
        assert "data: " in result
        assert result.endswith("\n\n")

        # Check some key fields exist in the JSON string:
        data_json = response.model_dump_json()
        for key in response.__class__.model_fields:
            assert str(getattr(response, key, "")) in data_json or key in data_json


def test_get_sse_event_logs_exception(monkeypatch, dummy_response_objects):
    intermediate_resp, _, _ = dummy_response_objects  # Unpack just the IntermediateTaskResponse

    # Monkeypatch to simulate serialization failure
    def raise_error(self):
        raise RuntimeError("forced_error")

    monkeypatch.setattr(type(intermediate_resp), "model_dump_json", raise_error)

    # Patch the correct logger used inside the function
    with patch("sk_agents.utils.logger") as mock_logger:
        get_sse_event_for_response(intermediate_resp)
        mock_logger.exception.assert_called_once_with("Failed to serialize SSE event for response")
