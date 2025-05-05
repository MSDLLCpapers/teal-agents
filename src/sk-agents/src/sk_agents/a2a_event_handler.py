import logging
from contextlib import nullcontext
from typing import Any

from redis import Redis
from ska_utils import (
    RedisStreamsEventHandler,
    get_telemetry,
    AppConfig,
    RedisStreamsEventPublisher,
)

from sk_agents.a2a_types import (
    A2AInvokeEvent,
    A2ANonRecoverableError,
    A2AErrorResponse,
    A2AEventType,
)
from sk_agents.configs import TA_REDIS_HOST, TA_REDIS_PORT
from sk_agents.ska_types import BaseConfig, BaseHandler
from sk_agents.skagents import handle as skagents_handle
from sk_agents.utils import invoke_response_to_a2a_event


class A2AEventHandler(RedisStreamsEventHandler[A2AInvokeEvent]):
    def __init__(self, app_config: AppConfig, config: BaseConfig, root_handler: str):
        self._app_config = app_config
        self._config = config
        self._root_handler = root_handler

        super().__init__(
            topic_name=f"{self._config.name}/{self._config.version}",
            r=Redis(
                host=app_config.get(TA_REDIS_HOST.env_name),
                port=int(app_config.get(TA_REDIS_PORT.env_name)),
            ),
            event_types=A2AInvokeEvent,
        )
        self._logger = logging.getLogger(__name__)
        self._publisher = RedisStreamsEventPublisher(self._r)

    async def process_event(self, event: A2AInvokeEvent) -> None:
        try:
            st = get_telemetry()
            with (
                st.tracer.start_as_current_span(
                    f"{self._config.name}-{str(self._config.version)}-invoke",
                )
                if st.telemetry_enabled()
                else nullcontext()
            ):
                authorization = A2AEventHandler._authorize_task(event)
                handler = self._get_handler(event.event_id, authorization)
                inv_inputs = event.event_data.__dict__
                return await self._invoke_appropriately(
                    event.event_type, event.event_id, handler, inv_inputs
                )
        except A2ANonRecoverableError:
            return None
        except Exception as e:
            self._logger.error(f"Unrecoverable exception: {e}")
            self._logger.error("Message dropped")
            return None

    async def _invoke_appropriately(
        self,
        event_type: A2AEventType,
        event_id: str,
        handler: BaseHandler,
        inputs: dict[str, Any],
    ) -> None:
        if event_type == A2AEventType.INVOKE_STREAM:
            return await self._invoke_stream(event_id, handler, inputs)
        elif event_type == A2AEventType.INVOKE:
            return await self._invoke(event_id, handler, inputs)
        else:
            self._publish_error_event(event_id, 400, f"Invalid event type{event_type}")
            raise A2ANonRecoverableError(f"Invalid event type{event_type}")

    async def _publish_stream(
        self, event_id: str, handler: BaseHandler, inputs: dict[str, Any]
    ) -> None:
        # noinspection PyTypeChecker
        async for result in handler.invoke_stream(inputs):
            self._publish_task_event(event_id, invoke_response_to_a2a_event(result))

    async def _invoke_stream(
        self, event_id: str, handler: BaseHandler, inputs: dict[str, Any]
    ) -> None:
        try:
            await self._publish_stream(event_id, handler, inputs)
        except Exception as e:
            self._publish_error_event(event_id, 500, str(e))
            raise A2ANonRecoverableError(str(e)) from e

    async def _invoke(
        self, event_id: str, handler: BaseHandler, inputs: dict[str, Any]
    ) -> None:
        try:
            output = await handler.invoke(inputs=inputs)
            self._publish_task_event(event_id, invoke_response_to_a2a_event(output))
        except Exception as e:
            self._publish_error_event(event_id, 500, str(e))
            raise A2ANonRecoverableError(str(e)) from e

    def _get_handler(self, event_id: str, authorization: str):
        if self._root_handler == "skagents":
            try:
                return skagents_handle(self._config, self._app_config, authorization)
            except Exception as e:
                self._publish_error_event(event_id, 500, str(e))
                raise A2ANonRecoverableError(str(e)) from e
        else:
            self._publish_error_event(
                event_id, 500, f"Unknown apiVersion: {self._config.apiVersion}"
            )
            raise A2ANonRecoverableError(
                f"Unknown apiVersion: {self._config.apiVersion}"
            )

    def _publish_error_event(self, event_id: str, status_code: int, message: str):
        self._publish_task_event(
            event_id,
            invoke_response_to_a2a_event(
                A2AErrorResponse(
                    status_code=status_code,
                    detail=message,
                )
            ),
        )

    def _publish_task_event(self, event_id: str, event: str):
        self._publisher.publish_event(
            topic_name=f"{self._topic_name}/{event_id}", event_data=event
        )

    @staticmethod
    def _authorize_task(event: A2AInvokeEvent) -> str:
        # TODO - How to retrieve authorization token?
        #  If the task is not authorized, raise NonRecoverableError
        return "dummy-token"
