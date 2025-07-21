from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from collab_orchestrator import (
    AbortResult,
    ErrorResponse,
    EventType,
    PlanningFailedException,
    PlanningHandler,
)


@pytest.fixture
def mock_telemetry():
    telemetry = MagicMock()
    telemetry.telemetry_enabled.return_value = True
    telemetry.tracer.start_as_current_span.return_value.__enter__ = MagicMock()
    telemetry.tracer.start_as_current_span.return_value.__exit__ = MagicMock()
    return telemetry


@pytest.fixture
def mock_config():
    config = MagicMock()
    config.spec = MagicMock()
    config.spec.human_in_the_loop = False
    config.spec.hitl_timeout = 0
    config.spec.model_dump.return_value = {}
    config.service_name = "test_service"
    config.version = "1.0.0"
    return config


@pytest.fixture
def mock_config_hitl():
    config = MagicMock()
    config.spec = MagicMock()
    config.spec.human_in_the_loop = True
    config.spec.hitl_timeout = 30
    config.spec.model_dump.return_value = {}
    config.service_name = "test_service"
    config.version = "1.0.0"
    return config


@pytest.fixture
def mock_agent_gateway():
    return MagicMock()


@pytest.fixture
def mock_base_agent_builder():
    builder = MagicMock()
    builder.build_agent = AsyncMock()
    return builder


@pytest.fixture
def mock_task_agents_bases():
    return [MagicMock()]


@pytest.fixture
def mock_task_agents():
    return [MagicMock()]


@pytest.fixture
def planning_handler(
    mock_telemetry,
    mock_config,
    mock_agent_gateway,
    mock_base_agent_builder,
    mock_task_agents_bases,
    mock_task_agents,
):
    return PlanningHandler(
        mock_telemetry,
        mock_config,
        mock_agent_gateway,
        mock_base_agent_builder,
        mock_task_agents_bases,
        mock_task_agents,
    )


@pytest.fixture
@patch("collab_orchestrator.planning_handler.planning_handler.PendingPlanStore")
def planning_handler_hitl(
    mock_pending_plan_store,
    mock_telemetry,
    mock_config_hitl,
    mock_agent_gateway,
    mock_base_agent_builder,
    mock_task_agents_bases,
    mock_task_agents,
):
    mock_store_instance = MagicMock()
    mock_pending_plan_store.return_value = mock_store_instance

    handler = PlanningHandler(
        mock_telemetry,
        mock_config_hitl,
        mock_agent_gateway,
        mock_base_agent_builder,
        mock_task_agents_bases,
        mock_task_agents,
    )
    handler.store = mock_store_instance
    return handler


def test_init_without_hitl(planning_handler):
    assert planning_handler.plan_manager is None
    assert planning_handler.planning_agent is None
    assert planning_handler.stream_tokens is False
    assert planning_handler.hitl is False
    assert planning_handler.timeout == 0
    assert planning_handler.store is None


def test_init_with_hitl(planning_handler_hitl):
    assert planning_handler_hitl.hitl is True
    assert planning_handler_hitl.timeout == 30
    assert planning_handler_hitl.store is not None


def test_start_span_with_telemetry_enabled(planning_handler):
    planning_handler._start_span("test_span", {"key": "value"})
    planning_handler.t.tracer.start_as_current_span.assert_called_once_with(
        name="test_span", attributes={"key": "value"}
    )


def test_start_span_with_telemetry_disabled(planning_handler):
    planning_handler.t.telemetry_enabled.return_value = False
    planning_handler._start_span("test_span")
    planning_handler.t.tracer.start_as_current_span.assert_not_called()


def test_start_span_with_none_attributes(planning_handler):
    planning_handler._start_span("test_span", None)
    planning_handler.t.tracer.start_as_current_span.assert_called_once_with(
        name="test_span", attributes=None
    )


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.planning_handler.PlanningSpec")
@patch("collab_orchestrator.planning_handler.planning_handler.PlanningAgent")
@patch("collab_orchestrator.planning_handler.planning_handler.PlanManager")
async def test_initialize(
    mock_plan_manager, mock_planning_agent, mock_planning_spec, planning_handler
):
    # Setup mocks
    mock_spec = MagicMock()
    mock_spec.planning_agent = MagicMock()
    mock_spec.stream_tokens = True
    mock_planning_spec.model_validate.return_value = mock_spec

    mock_agent_base = MagicMock()
    planning_handler.base_agent_builder.build_agent.return_value = mock_agent_base

    mock_planning_agent_instance = MagicMock()
    mock_planning_agent.return_value = mock_planning_agent_instance

    mock_plan_manager_instance = MagicMock()
    mock_plan_manager.return_value = mock_plan_manager_instance

    # Execute
    await planning_handler.initialize()

    # Verify
    mock_planning_spec.model_validate.assert_called_once()
    planning_handler.base_agent_builder.build_agent.assert_called_once_with(
        mock_spec.planning_agent
    )
    mock_planning_agent.assert_called_once_with(
        agent=mock_agent_base, gateway=planning_handler.agent_gateway
    )
    mock_plan_manager.assert_called_once_with(mock_planning_agent_instance)
    assert planning_handler.planning_agent == mock_planning_agent_instance
    assert planning_handler.plan_manager == mock_plan_manager_instance
    assert planning_handler.stream_tokens is True


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.planning_handler.StepExecutor")
@patch("collab_orchestrator.planning_handler.planning_handler.new_event_response")
@patch("collab_orchestrator.planning_handler.planning_handler.uuid")
async def test_invoke_success_no_hitl(
    mock_uuid, mock_new_event_response, mock_step_executor, planning_handler
):
    # Setup mocks
    mock_uuid.uuid4.return_value.hex = "test-uuid"

    mock_chat_history = MagicMock()
    mock_chat_history.session_id = "test-session"

    mock_plan = MagicMock()
    mock_plan.steps = [MagicMock()]
    mock_plan.steps[0].step_tasks = [MagicMock()]
    mock_plan.steps[0].step_tasks[0].result = "test result"

    planning_handler.plan_manager = MagicMock()
    planning_handler.plan_manager.generate_plan = AsyncMock(return_value=mock_plan)

    mock_step_executor_instance = MagicMock()
    mock_step_executor.return_value = mock_step_executor_instance

    async def mock_execute_step(*args):
        yield "step_result"

    mock_step_executor_instance.execute_step = mock_execute_step

    mock_event_responses = ["plan_response", "final_response"]
    mock_new_event_response.side_effect = mock_event_responses

    # Execute
    results = []
    async for result in planning_handler.invoke(mock_chat_history, "test request"):
        results.append(result)

    # Verify
    assert len(results) == 3
    assert results[0] == "plan_response"
    assert results[1] == "step_result"
    assert results[2] == "final_response"

    planning_handler.plan_manager.generate_plan.assert_called_once()
    mock_step_executor.assert_called_once_with(planning_handler.task_agents)


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.planning_handler.new_event_response")
@patch("collab_orchestrator.planning_handler.planning_handler.uuid")
async def test_invoke_planning_failed_exception(
    mock_uuid, mock_new_event_response, planning_handler
):
    # Setup mocks
    mock_uuid.uuid4.return_value.hex = "test-uuid"

    mock_chat_history = MagicMock()
    mock_chat_history.session_id = None

    planning_handler.plan_manager = MagicMock()
    planning_handler.plan_manager.generate_plan = AsyncMock(
        side_effect=PlanningFailedException("Planning failed")
    )

    mock_new_event_response.return_value = "error_response"

    # Execute
    results = []
    async for result in planning_handler.invoke(mock_chat_history, "test request"):
        results.append(result)

    # Verify
    assert len(results) == 1
    assert results[0] == "error_response"

    mock_new_event_response.assert_called_once()
    call_args = mock_new_event_response.call_args
    assert call_args[0][0] == EventType.ERROR
    assert isinstance(call_args[0][1], AbortResult)
    assert call_args[0][1].abort_reason == "Planning failed"


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.planning_handler.new_event_response")
@patch("collab_orchestrator.planning_handler.planning_handler.uuid")
async def test_invoke_general_exception(mock_uuid, mock_new_event_response, planning_handler):
    # Setup mocks
    mock_uuid.uuid4.return_value.hex = "test-uuid"

    mock_chat_history = MagicMock()
    mock_chat_history.session_id = "test-session"

    planning_handler.plan_manager = MagicMock()
    planning_handler.plan_manager.generate_plan = AsyncMock(side_effect=Exception("General error"))

    mock_new_event_response.return_value = "error_response"

    # Execute
    results = []
    async for result in planning_handler.invoke(mock_chat_history, "test request"):
        results.append(result)

    # Verify
    assert len(results) == 1
    assert results[0] == "error_response"

    mock_new_event_response.assert_called_once()
    call_args = mock_new_event_response.call_args
    assert call_args[0][0] == EventType.ERROR
    assert isinstance(call_args[0][1], ErrorResponse)
    assert call_args[0][1].detail == "General error"


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.planning_handler.new_event_response")
@patch("collab_orchestrator.planning_handler.planning_handler.uuid")
async def test_invoke_hitl_timeout(mock_uuid, mock_new_event_response, planning_handler_hitl):
    # Setup mocks
    mock_uuid.uuid4.return_value.hex = "test-uuid"

    mock_chat_history = MagicMock()
    mock_chat_history.session_id = "test-session"

    mock_plan = MagicMock()
    mock_plan.model_dump.return_value = {"plan": "data"}

    planning_handler_hitl.plan_manager = MagicMock()
    planning_handler_hitl.plan_manager.generate_plan = AsyncMock(return_value=mock_plan)

    planning_handler_hitl.store.save = AsyncMock()
    planning_handler_hitl.store.wait_for_decision = AsyncMock(return_value=None)

    mock_new_event_response.side_effect = ["plan_response", "timeout_response"]

    # Execute
    results = []
    async for result in planning_handler_hitl.invoke(mock_chat_history, "test request"):
        results.append(result)

    # Verify
    assert len(results) == 2
    assert results[0] == "plan_response"
    assert results[1] == "timeout_response"

    planning_handler_hitl.store.save.assert_called_once_with("test-session", {"plan": "data"})
    planning_handler_hitl.store.wait_for_decision.assert_called_once_with("test-session", 30)


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.planning_handler.new_event_response")
@patch("collab_orchestrator.planning_handler.planning_handler.uuid")
async def test_invoke_hitl_cancel(mock_uuid, mock_new_event_response, planning_handler_hitl):
    # Setup mocks
    mock_uuid.uuid4.return_value.hex = "test-uuid"

    mock_chat_history = MagicMock()
    mock_chat_history.session_id = "test-session"

    mock_plan = MagicMock()
    mock_plan.model_dump.return_value = {"plan": "data"}

    planning_handler_hitl.plan_manager = MagicMock()
    planning_handler_hitl.plan_manager.generate_plan = AsyncMock(return_value=mock_plan)

    planning_handler_hitl.store.save = AsyncMock()
    planning_handler_hitl.store.wait_for_decision = AsyncMock(return_value={"status": "cancel"})
    planning_handler_hitl.store.delete = AsyncMock()

    mock_new_event_response.side_effect = ["plan_response", "cancel_response"]

    # Execute
    results = []
    async for result in planning_handler_hitl.invoke(mock_chat_history, "test request"):
        results.append(result)

    # Verify
    assert len(results) == 2
    assert results[0] == "plan_response"
    assert results[1] == "cancel_response"

    planning_handler_hitl.store.delete.assert_called_once_with("test-session")


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.plan.Plan")
@patch("collab_orchestrator.planning_handler.planning_handler.StepExecutor")
@patch("collab_orchestrator.planning_handler.planning_handler.new_event_response")
@patch("collab_orchestrator.planning_handler.planning_handler.uuid")
async def test_invoke_hitl_edit(
    mock_uuid,
    mock_new_event_response,
    mock_step_executor,
    mock_plan_class,
    planning_handler_hitl,
):
    # Setup mocks
    mock_uuid.uuid4.return_value.hex = "test-uuid"

    mock_chat_history = MagicMock()
    mock_chat_history.session_id = "test-session"

    mock_plan = MagicMock()
    mock_plan.model_dump.return_value = {"plan": "data"}
    mock_plan.steps = [MagicMock()]
    mock_plan.steps[0].step_tasks = [MagicMock()]
    mock_plan.steps[0].step_tasks[0].result = "test result"

    mock_edited_plan = MagicMock()
    mock_edited_plan.steps = [MagicMock()]
    mock_edited_plan.steps[0].step_tasks = [MagicMock()]
    mock_edited_plan.steps[0].step_tasks[0].result = "edited result"

    mock_plan_class.model_validate.return_value = mock_edited_plan

    planning_handler_hitl.plan_manager = MagicMock()
    planning_handler_hitl.plan_manager.generate_plan = AsyncMock(return_value=mock_plan)

    planning_handler_hitl.store.save = AsyncMock()
    planning_handler_hitl.store.wait_for_decision = AsyncMock(
        return_value={"status": "edit", "edited_plan": {"edited": "plan"}}
    )
    planning_handler_hitl.store.delete = AsyncMock()

    mock_step_executor_instance = MagicMock()
    mock_step_executor.return_value = mock_step_executor_instance

    async def mock_execute_step(*args):
        yield "step_result"

    mock_step_executor_instance.execute_step = mock_execute_step()

    mock_new_event_response.side_effect = ["plan_response", "final_response"]

    # Execute
    results = []
    async for result in planning_handler_hitl.invoke(mock_chat_history, "test request"):
        results.append(result)

    # Verify
    assert len(results) == 2
    mock_plan_class.model_validate.assert_called_once_with({"edited": "plan"})
    planning_handler_hitl.store.delete.assert_called_once_with("test-session")


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.planning_handler.StepExecutor")
@patch("collab_orchestrator.planning_handler.planning_handler.new_event_response")
@patch("collab_orchestrator.planning_handler.planning_handler.uuid")
async def test_invoke_step_execution_exception(
    mock_uuid, mock_new_event_response, mock_step_executor, planning_handler
):
    # Setup mocks
    mock_uuid.uuid4.return_value.hex = "test-uuid"

    mock_chat_history = MagicMock()
    mock_chat_history.session_id = "test-session"

    mock_plan = MagicMock()
    mock_plan.steps = [MagicMock()]
    mock_plan.steps[0].step_tasks = [MagicMock()]
    mock_plan.steps[0].step_tasks[0].result = "test result"

    planning_handler.plan_manager = MagicMock()
    planning_handler.plan_manager.generate_plan = AsyncMock(return_value=mock_plan)

    mock_step_executor_instance = MagicMock()
    mock_step_executor.return_value = mock_step_executor_instance

    async def mock_execute_step_error(*args):
        raise Exception("Step execution failed")
        yield  # This line will never be reached, but makes it a generator

    mock_step_executor_instance.execute_step = mock_execute_step_error

    mock_new_event_response.side_effect = ["plan_response", "error_response", "final_response"]

    # Execute
    results = []
    async for result in planning_handler.invoke(mock_chat_history, "test request"):
        results.append(result)

    # Verify
    assert len(results) == 3
    assert results[0] == "plan_response"
    assert results[1] == "error_response"
    assert results[2] == "final_response"


@pytest.mark.asyncio
@patch("collab_orchestrator.planning_handler.planning_handler.StepExecutor")
@patch("collab_orchestrator.planning_handler.planning_handler.new_event_response")
@patch("collab_orchestrator.planning_handler.planning_handler.uuid")
async def test_invoke_with_streaming_tokens(
    mock_uuid, mock_new_event_response, mock_step_executor, planning_handler
):
    # Setup mocks
    mock_uuid.uuid4.return_value.hex = "test-uuid"

    mock_chat_history = MagicMock()
    mock_chat_history.session_id = "test-session"

    mock_plan = MagicMock()
    mock_plan.steps = [MagicMock()]
    mock_plan.steps[0].step_tasks = [MagicMock()]
    mock_plan.steps[0].step_tasks[0].result = "test result"

    planning_handler.plan_manager = MagicMock()
    planning_handler.plan_manager.generate_plan = AsyncMock(return_value=mock_plan)
    planning_handler.stream_tokens = True

    mock_step_executor_instance = MagicMock()
    mock_step_executor.return_value = mock_step_executor_instance

    async def mock_execute_step_sse(*args):
        yield "streaming_result"

    mock_step_executor_instance.execute_step_sse.return_value = mock_execute_step_sse()

    mock_new_event_response.side_effect = ["plan_response", "final_response"]

    # Execute
    results = []
    async for result in planning_handler.invoke(mock_chat_history, "test request"):
        results.append(result)

    # Verify
    assert len(results) == 3
    assert results[0] == "plan_response"
    assert results[1] == "streaming_result"
    assert results[2] == "final_response"

    mock_step_executor_instance.execute_step_sse.assert_called_once()
    mock_step_executor_instance.execute_step.assert_not_called()
