from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx_sse import ServerSentEvent

from collab_orchestrator import (
    AgentRequestEvent,
    ErrorResponse,
    EventType,
    ExecutableTask,
    InvokeResponse,
    PartialResponse,
    Step,
    StepExecutor,
    TaskStatus,
)
from collab_orchestrator.agents import TaskAgent


@pytest.fixture
def mock_task_agent():
    agent = MagicMock()
    agent.name = "test_agent"
    agent.version = "1.0"

    task_agent = MagicMock(spec=TaskAgent)
    task_agent.agent = agent
    task_agent.perform_task = AsyncMock(
        return_value=InvokeResponse(
            output_raw="test_result",
            token_usage={"total_tokens": 10, "prompt_tokens": 5, "completion_tokens": 5},
        )
    )
    task_agent.perform_task_sse = MagicMock()

    return task_agent


@pytest.fixture
def mock_executable_task():
    task = MagicMock(spec=ExecutableTask)
    task.task_id = "task_1"
    task.task_goal = "test_goal"
    task.task_agent = "test_agent:1.0"
    task.prerequisite_tasks = []
    task.result = None
    task.status = TaskStatus.TODO
    return task


@pytest.fixture
def mock_step(mock_executable_task):
    step = MagicMock(spec=Step)
    step.step_number = 1
    step.step_tasks = [mock_executable_task]
    return step


@pytest.fixture
def step_executor(mock_task_agent):
    with patch(
        "collab_orchestrator.planning_handler.step_executor.get_telemetry"
    ) as mock_telemetry:
        mock_telemetry.return_value.telemetry_enabled.return_value = False
        executor = StepExecutor([mock_task_agent])
        return executor


def test_init(mock_task_agent):
    with patch(
        "collab_orchestrator.planning_handler.step_executor.get_telemetry"
    ) as mock_get_telemetry:
        mock_telemetry = MagicMock()
        mock_get_telemetry.return_value = mock_telemetry

        executor = StepExecutor([mock_task_agent])

        assert "test_agent:1.0" in executor.task_agents
        assert executor.task_agents["test_agent:1.0"] == mock_task_agent
        assert executor.task_accumulator == {}
        assert executor.t == mock_telemetry


def test_task_to_pre_requisite():
    task = MagicMock(spec=ExecutableTask)
    task.task_goal = "test_goal"
    task.result = "test_result"

    prereq = StepExecutor._task_to_pre_requisite(task)

    assert prereq.goal == "test_goal"
    assert prereq.result == "test_result"


@pytest.mark.asyncio
async def test_execute_task_success(step_executor, mock_executable_task, mock_task_agent):
    session_id = "test_session"

    response = await step_executor._execute_task(session_id, mock_executable_task)

    assert response.output_raw == "test_result"
    assert mock_executable_task.result == "test_result"
    assert mock_executable_task.status == TaskStatus.DONE
    assert step_executor.task_accumulator["task_1"] == mock_executable_task
    mock_task_agent.perform_task.assert_called_once_with(session_id, "test_goal", [])


@pytest.mark.asyncio
async def test_execute_task_with_prerequisites(step_executor, mock_task_agent):
    session_id = "test_session"

    # Create prerequisite task
    prereq_task = MagicMock(spec=ExecutableTask)
    prereq_task.task_id = "prereq_task"
    prereq_task.task_goal = "prereq_goal"
    prereq_task.result = "prereq_result"
    step_executor.task_accumulator["prereq_task"] = prereq_task

    # Create main task
    main_task = MagicMock(spec=ExecutableTask)
    main_task.task_id = "main_task"
    main_task.task_goal = "main_goal"
    main_task.task_agent = "test_agent:1.0"
    main_task.prerequisite_tasks = ["prereq_task"]
    main_task.result = None
    main_task.status = TaskStatus.TODO

    await step_executor._execute_task(session_id, main_task)

    # Verify prerequisites were passed
    args, kwargs = mock_task_agent.perform_task.call_args
    session_id_arg, goal_arg, prerequisites_arg = args

    assert session_id_arg == session_id
    assert goal_arg == "main_goal"
    assert len(prerequisites_arg) == 1
    assert prerequisites_arg[0].goal == "prereq_goal"
    assert prerequisites_arg[0].result == "prereq_result"


@pytest.mark.asyncio
async def test_execute_task_agent_not_found(step_executor):
    task = MagicMock(spec=ExecutableTask)
    task.task_agent = "nonexistent_agent:1.0"

    with pytest.raises(ValueError, match="Task agent nonexistent_agent:1.0 not found"):
        await step_executor._execute_task("session", task)


@pytest.mark.asyncio
async def test_execute_task_with_telemetry(mock_task_agent):
    with patch(
        "collab_orchestrator.planning_handler.step_executor.get_telemetry"
    ) as mock_get_telemetry:
        mock_telemetry = MagicMock()
        mock_telemetry.telemetry_enabled.return_value = True
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span
        mock_telemetry.tracer = mock_tracer
        mock_get_telemetry.return_value = mock_telemetry

        executor = StepExecutor([mock_task_agent])

        task = MagicMock(spec=ExecutableTask)
        task.task_id = "task_1"
        task.task_goal = "test_goal"
        task.task_agent = "test_agent:1.0"
        task.prerequisite_tasks = []
        task.result = None
        task.status = TaskStatus.TODO

        await executor._execute_task("session", task)

        mock_tracer.start_as_current_span.assert_called_with(
            name="execute-task", attributes={"task": "task_1", "goal": "test_goal"}
        )


@pytest.mark.asyncio
async def test_execute_task_sse_partial_response(
    step_executor, mock_executable_task, mock_task_agent
):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    # Mock partial response
    partial_response = PartialResponse(content="partial content", output_partial="partial output")
    mock_task_agent.perform_task_sse.return_value = async_generator([partial_response])

    with patch(
        "collab_orchestrator.planning_handler.step_executor.new_event_response"
    ) as mock_new_event:
        mock_new_event.return_value = "mocked_event"

        results = []
        async for result in step_executor._execute_task_sse(
            session_id, source, request_id, mock_executable_task
        ):
            results.append(result)

        assert len(results) == 1
        mock_new_event.assert_called_with(EventType.PARTIAL_RESPONSE, partial_response)


@pytest.mark.asyncio
async def test_execute_task_sse_final_response(
    step_executor, mock_executable_task, mock_task_agent
):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    # Mock final response
    final_response = InvokeResponse(
        output_raw="final result",
        token_usage={
            "total_tokens": 10,
            "prompt_tokens": 5,
            "completion_tokens": 5,
        },
    )
    mock_task_agent.perform_task_sse.return_value = async_generator([final_response])

    with patch(
        "collab_orchestrator.planning_handler.step_executor.new_event_response"
    ) as mock_new_event:
        mock_new_event.return_value = "mocked_event"

        results = []
        async for result in step_executor._execute_task_sse(
            session_id, source, request_id, mock_executable_task
        ):
            results.append(result)

        assert len(results) == 1
        assert mock_executable_task.result == "final result"
        assert mock_executable_task.status == TaskStatus.DONE
        mock_new_event.assert_called_with(EventType.FINAL_RESPONSE, final_response)


@pytest.mark.asyncio
async def test_execute_task_sse_server_sent_event(
    step_executor, mock_executable_task, mock_task_agent
):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    # Mock ServerSentEvent
    sse_event = ServerSentEvent(event="test_event", data="test_data")
    mock_task_agent.perform_task_sse.return_value = async_generator([sse_event])

    results = []
    async for result in step_executor._execute_task_sse(
        session_id, source, request_id, mock_executable_task
    ):
        results.append(result)

    assert len(results) == 1
    assert results[0] == "event: test_event\ndata: test_data\n\n"


@pytest.mark.asyncio
async def test_execute_task_sse_unknown_response(
    step_executor, mock_executable_task, mock_task_agent
):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    # Mock unknown response
    unknown_response = "unknown response"
    mock_task_agent.perform_task_sse.return_value = async_generator([unknown_response])

    with patch(
        "collab_orchestrator.planning_handler.step_executor.new_event_response"
    ) as mock_new_event:
        mock_new_event.return_value = "mocked_event"

        results = []
        async for result in step_executor._execute_task_sse(
            session_id, source, request_id, mock_executable_task
        ):
            results.append(result)

        assert len(results) == 1
        # Verify error response was created
        call_args = mock_new_event.call_args
        assert call_args[0][0] == EventType.ERROR
        error_response = call_args[0][1]
        assert error_response.session_id == session_id
        assert error_response.source == source
        assert error_response.request_id == request_id
        assert error_response.status_code == 500
        assert "Unknown response type" in error_response.detail


@pytest.mark.asyncio
async def test_execute_task_sse_agent_not_found(step_executor):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    task = MagicMock(spec=ExecutableTask)
    task.task_agent = "nonexistent_agent:1.0"
    task.task_id = "test_task"
    task.task_goal = "test_goal"
    task.prerequisite_tasks = []

    with pytest.raises(ValueError, match="Task agent nonexistent_agent:1.0 not found"):
        async for _result in step_executor._execute_task_sse(session_id, source, request_id, task):
            pass


@pytest.mark.asyncio
async def test_execute_step_success(step_executor, mock_step, mock_task_agent):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    with patch(
        "collab_orchestrator.planning_handler.step_executor.new_event_response"
    ) as mock_new_event:
        mock_new_event.side_effect = lambda event_type, data: f"event:{event_type.value}:{data}"

        results = []
        async for result in step_executor.execute_step(session_id, source, request_id, mock_step):
            results.append(result)

        assert len(results) == 2  # AGENT_REQUEST + FINAL_RESPONSE

        # Verify AGENT_REQUEST event was generated
        mock_new_event.assert_any_call(
            EventType.AGENT_REQUEST,
            AgentRequestEvent(
                session_id=session_id,
                source=source,
                request_id=request_id,
                task_id="task_1",
                agent_name="test_agent:1.0",
                task_goal="test_goal",
            ),
        )

        # Verify task was executed
        mock_task_agent.perform_task.assert_called_once()

        # Verify task status was updated
        assert mock_step.step_tasks[0].status == TaskStatus.DONE
        assert mock_step.step_tasks[0].result == "test_result"


@pytest.mark.asyncio
async def test_execute_step_with_exception(step_executor, mock_step, mock_task_agent):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    # Make task execution raise an exception
    mock_task_agent.perform_task.side_effect = Exception("Test error")

    with patch(
        "collab_orchestrator.planning_handler.step_executor.new_event_response"
    ) as mock_new_event:
        mock_new_event.side_effect = lambda event_type, data: f"event:{event_type.value}:{data}"

        results = []
        async for result in step_executor.execute_step(session_id, source, request_id, mock_step):
            results.append(result)

        assert len(results) == 2  # AGENT_REQUEST + ERROR

        # Verify ERROR event was generated
        mock_new_event.assert_any_call(
            EventType.ERROR,
            ErrorResponse(
                session_id=session_id,
                source=source,
                request_id=request_id,
                status_code=500,
                detail="Test error",
            ),
        )


@pytest.mark.asyncio
async def test_execute_step_multiple_tasks(step_executor, mock_task_agent):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    # Create multiple tasks
    task1 = MagicMock(spec=ExecutableTask)
    task1.task_id = "task_1"
    task1.task_goal = "goal_1"
    task1.task_agent = "test_agent:1.0"
    task1.prerequisite_tasks = []
    task1.result = None
    task1.status = TaskStatus.TODO

    task2 = MagicMock(spec=ExecutableTask)
    task2.task_id = "task_2"
    task2.task_goal = "goal_2"
    task2.task_agent = "test_agent:1.0"
    task2.prerequisite_tasks = []
    task2.result = None
    task2.status = TaskStatus.TODO

    step = MagicMock(spec=Step)
    step.step_number = 1
    step.step_tasks = [task1, task2]

    with patch(
        "collab_orchestrator.planning_handler.step_executor.new_event_response"
    ) as mock_new_event:
        mock_new_event.side_effect = lambda event_type, data: f"event:{event_type.value}:{data}"

        results = []
        async for result in step_executor.execute_step(session_id, source, request_id, step):
            results.append(result)

        assert len(results) == 4  # 2 * (AGENT_REQUEST + FINAL_RESPONSE)

        # Verify both tasks were executed
        assert mock_task_agent.perform_task.call_count == 2

        # Verify both tasks were updated
        assert task1.status == TaskStatus.DONE
        assert task2.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_execute_step_with_telemetry(mock_task_agent):
    with patch(
        "collab_orchestrator.planning_handler.step_executor.get_telemetry"
    ) as mock_get_telemetry:
        mock_telemetry = MagicMock()
        mock_telemetry.telemetry_enabled.return_value = True
        mock_tracer = MagicMock()
        mock_span = MagicMock()
        mock_tracer.start_as_current_span.return_value = mock_span
        mock_telemetry.tracer = mock_tracer
        mock_get_telemetry.return_value = mock_telemetry

        executor = StepExecutor([mock_task_agent])

        task = MagicMock(spec=ExecutableTask)
        task.task_id = "task_1"
        task.task_goal = "test_goal"
        task.task_agent = "test_agent:1.0"
        task.prerequisite_tasks = []
        task.result = None
        task.status = TaskStatus.TODO

        step = MagicMock(spec=Step)
        step.step_number = 1
        step.step_tasks = [task]

        with patch(
            "collab_orchestrator.planning_handler.step_executor.new_event_response"
        ) as mock_new_event:
            mock_new_event.side_effect = lambda event_type, data: f"event:{event_type.value}:{data}"

            results = []
            async for result in executor.execute_step("session", "source", "request", step):
                results.append(result)

            calls = mock_tracer.start_as_current_span.call_args_list

            assert len(calls) >= 2

            execute_step_call = None
            execute_task_call = None

            for call in calls:
                args, kwargs = call
                if kwargs.get("name") == "execute-step":
                    execute_step_call = call
                elif kwargs.get("name") == "execute-task":
                    execute_task_call = call

            assert execute_step_call is not None
            _, kwargs = execute_step_call
            assert kwargs["name"] == "execute-step"
            assert kwargs["attributes"] == {"step": "1"}

            assert execute_task_call is not None
            _, kwargs = execute_task_call
            assert kwargs["name"] == "execute-task"
            assert kwargs["attributes"] == {"task": "task_1", "goal": "test_goal"}


@pytest.mark.asyncio
async def test_execute_step_sse_success(step_executor, mock_step, mock_task_agent):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    # Mock the SSE response
    final_response = InvokeResponse(
        output_raw="sse_result",
        token_usage={"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50},
    )
    mock_task_agent.perform_task_sse.return_value = async_generator([final_response])

    with patch(
        "collab_orchestrator.planning_handler.step_executor.new_event_response"
    ) as mock_new_event:
        mock_new_event.side_effect = lambda event_type, data: f"event:{event_type.value}:{data}"

        results = []
        async for result in step_executor.execute_step_sse(
            session_id, source, request_id, mock_step
        ):
            results.append(result)

        # Should have AGENT_REQUEST + FINAL_RESPONSE
        assert len(results) == 2


@pytest.mark.asyncio
async def test_execute_step_sse_multiple_tasks(step_executor, mock_task_agent):
    session_id = "test_session"
    source = "test_source"
    request_id = "test_request"

    # Create multiple tasks
    task1 = MagicMock(spec=ExecutableTask)
    task1.task_id = "task_1"
    task1.task_goal = "goal_1"
    task1.task_agent = "test_agent:1.0"
    task1.prerequisite_tasks = []
    task1.result = None
    task1.status = TaskStatus.TODO

    task2 = MagicMock(spec=ExecutableTask)
    task2.task_id = "task_2"
    task2.task_goal = "goal_2"
    task2.task_agent = "test_agent:1.0"
    task2.prerequisite_tasks = []
    task2.result = None
    task2.status = TaskStatus.TODO

    step = MagicMock(spec=Step)
    step.step_number = 1
    step.step_tasks = [task1, task2]

    # Mock SSE responses
    final_response1 = InvokeResponse(
        output_raw="result1",
        token_usage={"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50},
    )
    final_response2 = InvokeResponse(
        output_raw="result2",
        token_usage={"total_tokens": 100, "prompt_tokens": 50, "completion_tokens": 50},
    )

    # Create separate async generators for each task
    mock_task_agent.perform_task_sse.side_effect = [
        async_generator([final_response1]),
        async_generator([final_response2]),
    ]

    with patch(
        "collab_orchestrator.planning_handler.step_executor.new_event_response"
    ) as mock_new_event:
        mock_new_event.side_effect = lambda event_type, data: f"event:{event_type.value}:{data}"

        results = []
        async for result in step_executor.execute_step_sse(session_id, source, request_id, step):
            results.append(result)

        # Should have 2 * (AGENT_REQUEST + FINAL_RESPONSE)
        assert len(results) == 4


@pytest.mark.asyncio
async def test_merge_async_iterables(step_executor):
    # Create test iterables
    async def iter1():
        yield "a"
        yield "b"

    async def iter2():
        yield "c"
        yield "d"

    iterables = [iter1(), iter2()]

    results = []
    async for result in step_executor._merge_async_iterables(iterables):
        results.append(result)

    # Should contain all items from both iterables
    assert len(results) == 4
    assert set(results) == {"a", "b", "c", "d"}


@pytest.mark.asyncio
async def test_merge_async_iterables_empty(step_executor):
    results = []
    async for result in step_executor._merge_async_iterables([]):
        results.append(result)

    assert len(results) == 0


# Helper function to create async generators for testing
async def async_generator(items):
    for item in items:
        yield item
