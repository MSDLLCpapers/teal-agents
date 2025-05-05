import asyncio
import logging
import threading
import typing
import uuid
from abc import ABC, abstractmethod
from typing import TypeVar, Generic
from pydantic import BaseModel, TypeAdapter

from redis import Redis
from redis.exceptions import ResponseError

StreamsType = list[tuple[bytes, list[tuple[bytes, dict[bytes, bytes]]]]]

TEventType = TypeVar("TEventType")


class MaxWaitExceededError(Exception):
    pass


class RedisStreamsEventHandler(ABC, Generic[TEventType]):
    def __init__(
            self,
            topic_name: str,
            r: Redis,
            event_types: type[TEventType],
            max_message_wait: int = -1,
    ):
        self._topic_name = topic_name
        self._group_name = f"{self._topic_name}/consumers"
        self._consumer_name = str(uuid.uuid4().hex)
        self._r = r
        self._shutdown = True
        self._t: threading.Thread | None = None
        self._max_message_wait = max_message_wait
        self._logger = logging.getLogger(__name__)
        self._event_types = RedisStreamsEventHandler._validate_event_types(event_types)
        self._type_adapter = RedisStreamsEventHandler._get_type_adapter_for_event_types(event_types)

    @staticmethod
    def _get_type_adapter_for_event_types(event_types: type[TEventType]):
        try:
            return TypeAdapter(event_types)
        except Exception as e:
            raise TypeError(f"Failed to create TypeAdapter for {event_types!r}: {e}")

    @staticmethod
    def _validate_event_types(event_types: type[TEventType]) -> type[TEventType]:
        origin = typing.get_origin(event_types)
        is_valid = False
        if origin is typing.Union:
            args = typing.get_args(event_types)
            if args and all(RedisStreamsEventHandler._is_base_model_subclass(arg) for arg in args):
                is_valid = True
        elif origin is None:
            if RedisStreamsEventHandler._is_base_model_subclass(event_types):
                is_valid = True
        if not is_valid:
            raise TypeError(
                f"EventHandler 'event_types' must be a pydantic.BaseModel subclass "
                f"or a typing.Union of pydantic.BaseModel subclasses, "
                f"but got {event_types!r}"
            )
        return event_types

    @staticmethod
    def _is_base_model_subclass(t):
        return isinstance(t, type) and issubclass(t, BaseModel)

    def initialize(self):
        if not self._shutdown:
            raise RuntimeError("EventManager is already initialized.")

        self._t = threading.Thread(
            target=self._listen_and_process,
            name="EventManagerThread",
        )
        self._t.start()
        self._logger.info("Event handler started")

    def shutdown(self):
        if self._shutdown:
            raise RuntimeError("EventManager is already shut down.")

        self._shutdown = True
        self._t.join(timeout=30.0)
        if self._t.is_alive():
            self._logger.warning("Timed out waiting for event handler shutdown.")

    @abstractmethod
    async def process_event(self, event: TEventType) -> None:
        pass

    def _create_consumer_group(self):
        try:
            result = self._r.xgroup_create(self._topic_name, self._group_name, 0, True)
            if result:
                self._logger.info(
                    f"Consumer group {self._group_name} created successfully"
                )
            else:
                raise RuntimeError("Failed to create consumer group")
        except ResponseError as e:
            if "BUSYGROUP Consumer Group name already exists" in str(e):
                self._logger.info(f"Consumer group {self._group_name} already exists")
            else:
                raise e

    # noinspection PyTypeChecker
    def _decode_event(self, event: StreamsType) -> (str, TEventType):
        try:
            event_id = event[0][1][0][0].decode()
            event_data_str = event[0][1][0][1][b"event_data"].decode()
            invoke_event = self._type_adapter.validate_json(event_data_str)
            return event_id, invoke_event
        except Exception as e:
            self._logger.error(f"Error decoding event: {e}")
            raise e

    def _get_next_message(self) -> TEventType | None:
        block = (self._max_message_wait * 1000) if self._max_message_wait > -1 else 1000

        result: StreamsType = self._r.xreadgroup(
            streams={self._topic_name: ">"},
            groupname=self._group_name,
            consumername=self._consumer_name,
            count=1,
            block=block,
        )

        if not result:
            if self._max_message_wait > -1:
                raise MaxWaitExceededError()
            else:
                return None

        try:
            event_id, invoke_event = self._decode_event(result)
            self._r.xack(self._topic_name, self._group_name, event_id)
            return invoke_event
        except Exception as e:
            self._logger.error(f"Error decoding event {e} - Possible abandoned message")
            return None

    def _listen_and_process(self):
        asyncio.run(self._a_listen_and_process())

    async def _a_listen_and_process(self):
        self._shutdown = False
        try:
            self._create_consumer_group()
        except Exception as e:
            self._shutdown = True
            raise e

        while not self._shutdown:
            try:
                event = self._get_next_message()
            except MaxWaitExceededError:
                self._logger.info("Max wait time exceeded, no message received")
                self._shutdown = True
                break
            if not event:
                continue
            await self.process_event(event)
        self._logger.info("Event handler shutdown completed")
