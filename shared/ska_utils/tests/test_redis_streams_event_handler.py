from typing import Union
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import BaseModel, TypeAdapter
from redis import Redis
from redis.exceptions import ResponseError

from ska_utils import MaxWaitExceededError, RedisStreamsEventHandler


class EventModel(BaseModel):
    event_data: str


class AnotherEventModel(BaseModel):
    event_id: int


class InvalidType:
    pass


class ConcreateRedisStreamsEventHandler(RedisStreamsEventHandler[EventModel]):
    processed_events = []

    async def process_event(self, event: EventModel) -> None:
        self.processed_events.append(event.event_data)


@pytest.fixture
def mock_redis():
    return MagicMock(spec=Redis)


@pytest.fixture
def event_handler(mock_redis):
    with patch("threading.Thread"):
        yield ConcreateRedisStreamsEventHandler(
            topic_name="test_topic", r=mock_redis, event_types=EventModel, max_message_wait=5
        )


def test_initialization(event_handler):
    assert event_handler._topic_name == "test_topic"
    assert event_handler._group_name == "test_topic/consumers"
    assert isinstance(event_handler._consumer_name, str)
    assert event_handler._max_message_wait == 5


def test_get_type_adapter_success(event_handler):
    adapter = event_handler._get_type_adapter_for_event_types(EventModel)
    assert isinstance(adapter, TypeAdapter)


def test_get_type_adapter_failure(event_handler):
    with pytest.raises(TypeError):
        event_handler._get_type_adapter_for_event_types(InvalidType)


def test_validate_event_types_valid():
    assert RedisStreamsEventHandler._validate_event_types(EventModel) == EventModel


def test_validate_union_of_valid_event_types():
    result = RedisStreamsEventHandler._validate_event_types(Union[BaseModel, AnotherEventModel])  # noqa: UP007
    assert result == Union[BaseModel | AnotherEventModel]  # noqa: UP007


def test_validate_event_types_invalid():
    with pytest.raises(TypeError, match="must be a pydantic.BaseModel subclass"):
        RedisStreamsEventHandler._validate_event_types(int)


def test_initialize(event_handler):
    event_handler._shutdown = True
    event_handler.initialize()
    assert event_handler._t is not None


def test_initialize_already_initialized(event_handler):
    event_handler._shutdown = False
    with pytest.raises(RuntimeError, match="EventManager is already initialized."):
        event_handler.initialize()


def test_shutdown(event_handler):
    event_handler.initialize()
    event_handler.shutdown()
    assert event_handler._shutdown
    assert event_handler._t is None


def test_shutdown_already_shutdown(event_handler):
    event_handler._shutdown = True
    with pytest.raises(RuntimeError, match="EventManager is already shut down."):
        event_handler.shutdown()


def test_create_consumer_group_success(event_handler):
    event_handler._r.xgroup_create.return_value = True
    event_handler._create_consumer_group()
    event_handler._r.xgroup_create.assert_called_once_with(
        event_handler._topic_name, event_handler._group_name, 0, True
    )


def test_create_consumer_group_busy_group(event_handler):
    event_handler._r.xgroup_create.side_effect = ResponseError(
        "BUSYGROUP Consumer Group name already exists"
    )
    event_handler._create_consumer_group()  # Should not raise an error


def test_create_consumer_group_failure(event_handler):
    event_handler._r.xgroup_create.side_effect = ResponseError("Some other error")
    with pytest.raises(ResponseError):
        event_handler._create_consumer_group()


def test_create_consumer_group_runtime_error(event_handler):
    event_handler._r.xgroup_create.return_value = False
    with pytest.raises(RuntimeError):
        event_handler._create_consumer_group()


def test_decode_event(event_handler):
    event = [(b"1", [(b"0", {b"event_data": b'{"event_data": "test"}'})])]
    event_id, decoded_event = event_handler._decode_event(event)
    assert event_id == "0"
    assert decoded_event.event_data == "test"


def test_decode_event_error(event_handler):
    event = [(b"1", [(b"0", {b"event_data": b'{"event_data": "test"}'})])]
    event_handler._type_adapter.validate_json = MagicMock(side_effect=Exception("Decode error"))
    with pytest.raises(Exception, match="Decode error"):
        event_handler._decode_event(event)


def test_get_next_message_no_message(event_handler):
    event_handler._max_message_wait = -1
    event_handler._r.xreadgroup.return_value = []
    result = event_handler._get_next_message()
    assert result is None


def test_get_next_message_with_message(event_handler):
    event = [(b"1", [(b"1", {b"event_data": b'{"event_data": "test"}'})])]
    event_handler._r.xreadgroup.return_value = event
    event_handler._r.xack = MagicMock()
    result = event_handler._get_next_message()
    assert result.event_data == "test"
    event_handler._r.xack.assert_called_once()


def test_get_next_message_max_wait_exceeded(event_handler):
    event_handler._r.xreadgroup.side_effect = MaxWaitExceededError()
    with pytest.raises(MaxWaitExceededError):
        event_handler._get_next_message()


def test_get_next_message_decoding_error(event_handler):
    mock_result = {("test_topic", "1"): ("1", "test_event")}
    event_handler._r.xreadgroup.return_value = mock_result
    with patch.object(event_handler, "_decode_event", side_effect=Exception("Decoding error")):
        invoke_event = event_handler._get_next_message()
        assert invoke_event is None


def test_listen_and_process(event_handler):
    with patch.object(
        event_handler, "_a_listen_and_process", new_callable=AsyncMock
    ) as mock_a_listen_and_process:
        event_handler._listen_and_process()
        mock_a_listen_and_process.assert_called_once()


@pytest.mark.asyncio
async def test_a_listen_and_process(event_handler):
    event = [(b"1", [(b"1", {b"event_data": b'{"event_data": "test"}'})])]
    event_handler._r.xreadgroup.return_value = event
    event_handler.initialize()

    async def mock_process_event(event):
        assert event.event_data == "test"
        event_handler._shutdown = True

    event_handler.process_event = AsyncMock(mock_process_event)
    event_handler._r.xreadgroup.side_effect = [event, []]
    await event_handler._a_listen_and_process()
    assert event_handler._shutdown


@pytest.mark.asyncio
async def test_a_listen_and_process_consumer_group_creating_failure(event_handler):
    event_handler._create_consumer_group = Mock(side_effect=Exception("Creation failed"))
    with pytest.raises(Exception, match="Creation failed"):
        await event_handler._a_listen_and_process()
    assert event_handler._shutdown is True
