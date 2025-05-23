import pytest

from sk_agents.exceptions import AgentInvokeException, InvalidConfigException
from sk_agents.extra_data_collector import ExtraDataCollector
from sk_agents.ska_types import BaseConfig, InvokeResponse, TokenUsage
from sk_agents.skagents.kernel_builder import KernelBuilder
from sk_agents.skagents.v1.config import AgentConfig
from sk_agents.skagents.v1.sequential.config import Spec, TaskConfig
from sk_agents.skagents.v1.sequential.sequential_skagents import SequentialSkagents
from sk_agents.skagents.v1.sequential.task import Task
from sk_agents.skagents.v1.sequential.task_builder import TaskBuilder
from sk_agents.skagents.v1.sk_agent import SKAgent


@pytest.fixture
def config():
    test_agent = AgentConfig(
        name="test agent",
        model="test model",
        system_prompt="test prompt",
        plugins=None,
        remote_plugins=None,
    )

    task = TaskConfig(
        name="test name task",
        task_no=1,
        description="test task description",
        instructions="test task instruction",
        agent="test agent",
    )
    task_2 = TaskConfig(
        name="task # 2",
        task_no=2,
        description="test task description",
        instructions="test task instruction",
        agent="test agent",
    )
    config = BaseConfig(
        apiVersion="v1",
        description="test-agent",
        service_name="TestAgent",
        version=0.1,
        input_type="BaseInput",
        output_type=None,
        spec=Spec(agents=[test_agent], tasks=[task, task_2]),
    )
    return config


@pytest.fixture
def mock_kernel_builder(mocker):
    return mocker.Mock(spec=KernelBuilder)


@pytest.fixture
def mock_task_builder(mocker):
    task_builder = mocker.AsyncMock(spec=TaskBuilder)
    agent_mock = mocker.Mock(spec=SKAgent)
    build_task_return = Task(
        name="test task",
        description="test",
        instructions="run test",
        agent=agent_mock,
        extra_data_collector=None,
    )
    task_builder.build_task.return_value = build_task_return

    return task_builder


@pytest.fixture
def task_invoke_response_mock(mocker):
    mock_response = InvokeResponse(
        token_usage=TokenUsage(completion_tokens=10, prompt_tokens=10, total_tokens=20),
        extra_data=None,
        output_raw="raw output",
    )

    async def mock_invoke(*args, **kwargs):
        return mock_response

    mocker.patch("sk_agents.skagents.v1.sequential.task.Task.invoke", side_effect=mock_invoke)
    return mock_response


@pytest.fixture
def task_invoke_exception_response_mock(mocker):
    async def mock_error(*args, **kwargs):
        raise Exception(" **** Mocked error while invoking agent ****")

    mocker.patch("sk_agents.skagents.v1.sequential.task.Task.invoke", side_effect=mock_error)


@pytest.fixture
def mock_extra_data_collector(mocker):
    collector = mocker.Mock(spec=ExtraDataCollector)
    collector.return_value.add_extra_data_items.return_value = None
    collector.return_value.get_extra_data.return_value = None

    mocker.patch(
        "sk_agents.skagents.v1.sequential.sequential_skagents.ExtraDataCollector", new=collector
    )

    return collector


class MockMessage:
    content: str = "This is a Mock Message"


class MockChatHistory:
    messages: list = [MockMessage(), MockMessage()]


@pytest.mark.asyncio
async def test_sequential_invoke(
    config,
    mock_task_builder,
    mock_kernel_builder,
    task_invoke_response_mock,
    mock_extra_data_collector,
    mocker,
) -> None:
    """
    Test:
    ExtraDataCollecotr, ChatHistory are called
    Return type: InvokeResponse
    Task count and token metrics change
    Response output_raw is last message in chat history
    """

    skagents = SequentialSkagents(config, mock_kernel_builder, mock_task_builder)
    test_input = {"test_input_key": "test_input_value", "chat_history": []}
    mock_parse_task_inputs = mocker.patch.object(
        SequentialSkagents,
        "_parse_task_inputs",
        return_value={"parsed_inputs": test_input["test_input_key"]},
    )
    mock_parse_chat_history = mocker.patch(
        "sk_agents.skagents.v1.sequential.sequential_skagents.parse_chat_history",
        return_value=MockChatHistory,
    )
    mocker.patch(
        "sk_agents.skagents.v1.sequential.sequential_skagents.ChatHistory", new=MockChatHistory
    )

    response = await skagents.invoke(inputs=test_input)

    mock_extra_data_collector.assert_called()
    mock_parse_chat_history.assert_called()
    mock_parse_task_inputs.assert_called()

    assert isinstance(response, InvokeResponse)
    assert response.token_usage.completion_tokens > 0
    assert response.token_usage.prompt_tokens > 0
    assert response.token_usage.total_tokens > 0
    assert response.output_raw == "This is a Mock Message"


@pytest.mark.asyncio
async def test_sequential_invoke_with_output_type(
    config,
    mock_task_builder,
    mock_kernel_builder,
    task_invoke_response_mock,
    mock_extra_data_collector,
    mocker,
) -> None:
    """
    Test:
    Tranform output if required is called when config.output_type is set
    """

    config.output_type = "mock_type"
    mock_parse_task_inputs = mocker.patch.object(
        SequentialSkagents, "_transform_output_if_required"
    )
    skagents = SequentialSkagents(config, mock_kernel_builder, mock_task_builder)

    test_input = {"test_input_key": "test_input_value", "chat_history": []}

    mock_parse_task_inputs = mocker.patch.object(
        SequentialSkagents,
        "_parse_task_inputs",
        return_value={"parsed_inputs": test_input["test_input_key"]},
    )
    mocker.patch(
        "sk_agents.skagents.v1.sequential.sequential_skagents.parse_chat_history",
        return_value=MockChatHistory,
    )
    mocker.patch(
        "sk_agents.skagents.v1.sequential.sequential_skagents.ChatHistory", new=MockChatHistory
    )

    await skagents.invoke(inputs=test_input)

    mock_parse_task_inputs.assert_called()


def test_init_sequential(config, mock_task_builder, mock_kernel_builder) -> None:
    """
    Test:
    SequentialSkagents init
    """
    skagents = SequentialSkagents(config, mock_kernel_builder, mock_task_builder)
    assert skagents is not None
    assert skagents.tasks is not None


def test_invalid_agent_config_spec(config, mock_task_builder, mock_kernel_builder) -> None:
    """
    Test:
    InvalidConfigException is raised
    """
    delattr(config, "spec")

    with pytest.raises(InvalidConfigException):
        SequentialSkagents(config, mock_kernel_builder, mock_task_builder)


def test_invalid_agent_tasks(config, mock_task_builder, mock_kernel_builder) -> None:
    """
    Test:
    SequentialSkagents without tasks
    """
    config.spec.tasks = []
    with pytest.raises(InvalidConfigException):
        SequentialSkagents(config, mock_kernel_builder, mock_task_builder)


@pytest.mark.asyncio
async def test_sequential_invoke_exception_error(
    config,
    mock_task_builder,
    mock_kernel_builder,
    task_invoke_exception_response_mock,
    mock_extra_data_collector,
    mocker,
) -> None:
    """
    Test:
    AgentInvokeException error is raised
    """

    skagents = SequentialSkagents(config, mock_kernel_builder, mock_task_builder)
    test_input = {"test_input_key": "test_input_value", "chat_history": []}
    mocker.patch.object(
        SequentialSkagents,
        "_parse_task_inputs",
        return_value={"parsed_inputs": test_input["test_input_key"]},
    )
    mocker.patch(
        "sk_agents.skagents.v1.sequential.sequential_skagents.parse_chat_history",
        return_value=MockChatHistory,
    )
    mocker.patch(
        "sk_agents.skagents.v1.sequential.sequential_skagents.ChatHistory", new=MockChatHistory
    )
    with pytest.raises(AgentInvokeException):
        await skagents.invoke(inputs=test_input)
