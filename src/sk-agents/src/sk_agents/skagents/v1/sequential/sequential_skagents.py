import json
import logging
import uuid
from collections.abc import AsyncIterable
from copy import deepcopy
from typing import Any

from semantic_kernel.contents.chat_history import ChatHistory

from sk_agents.exceptions import AgentInvokeException, InvalidConfigException
from sk_agents.extra_data_collector import ExtraDataCollector, ExtraDataPartial
from sk_agents.ska_types import (
    BaseConfig,
    BaseHandler,
    IntermediateTaskResponse,
    InvokeResponse,
    PartialResponse,
    TokenUsage,
)
from sk_agents.skagents.kernel_builder import KernelBuilder
from sk_agents.skagents.v1.sequential.config import Config
from sk_agents.skagents.v1.sequential.output_transformer import OutputTransformer
from sk_agents.skagents.v1.sequential.task_builder import TaskBuilder
from sk_agents.skagents.v1.utils import get_token_usage_for_response, parse_chat_history
from sk_agents.type_loader import get_type_loader

logger = logging.getLogger(__name__)


class SequentialSkagents(BaseHandler):
    def __init__(
        self,
        config: BaseConfig,
        kernel_builder: KernelBuilder,
        task_builder: TaskBuilder,
    ):
        if hasattr(config, "spec"):
            self.config = Config(config=config)
        else:
            raise InvalidConfigException(
                f"Invalid config: Expected 'spec' attribute, got {config.__dict__}"
            )

        self.name = config.service_name
        self.version = config.version

        self.kernel_builder = kernel_builder

        task_configs = self.config.get_tasks()
        if not task_configs:
            raise InvalidConfigException(
                f"Invalid agent configuration: Expected 'spec.tasks', got {config.spec.tasks}"
            )
        sorted_configs = sorted(task_configs, key=lambda x: x.task_no)
        self.tasks = []
        for i in range(len(sorted_configs) - 1):
            task_config = sorted_configs[i]
            self.tasks.append(task_builder.build_task(task_config, self.config.get_agents()))
        self.tasks.append(
            task_builder.build_task(
                sorted_configs[-1],
                self.config.get_agents(),
                self.config.config.output_type,
            )
        )

    async def _transform_output_if_required(self, response: InvokeResponse) -> InvokeResponse:
        if self.tasks[-1].agent.so_supported():
            type_loader = get_type_loader()
            output_type = type_loader.get_type(self.config.config.output_type)
            response.output_pydantic = output_type(**json.loads(response.output_raw))
            return response
        else:
            return await self._transform_output(response, self.config.config.output_type)

    async def _transform_output(
        self, current_response: InvokeResponse, output_type_str: str
    ) -> InvokeResponse:
        output_transformer = OutputTransformer(self.kernel_builder)

        transformed_response = await output_transformer.transform_output(
            current_response.output_raw, output_type_str
        )

        type_loader = get_type_loader()
        output_type = type_loader.get_type(output_type_str)
        response = InvokeResponse[output_type](
            token_usage=TokenUsage(
                completion_tokens=current_response.token_usage.completion_tokens
                + transformed_response.token_usage.completion_tokens,
                prompt_tokens=current_response.token_usage.prompt_tokens
                + transformed_response.token_usage.prompt_tokens,
                total_tokens=current_response.token_usage.total_tokens
                + transformed_response.token_usage.total_tokens,
            ),
            extra_data=current_response.extra_data,
            output_raw=current_response.output_raw,
            output_pydantic=transformed_response.output_pydantic,
        )
        return response

    @staticmethod
    def _parse_task_inputs(
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        if inputs is not None:
            task_inputs = deepcopy(inputs)
            if "chat_history" in task_inputs:
                del task_inputs["chat_history"]
        else:
            task_inputs = None
        return task_inputs

    async def invoke_stream(
        self, inputs: dict[str, Any] | None = None
    ) -> AsyncIterable[PartialResponse | IntermediateTaskResponse | InvokeResponse]:
        collector = ExtraDataCollector()
        # Initialize tasks count and token metrics
        task_no = 0
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0
        final_response = []
        # Initialize and parse the chat history and task inputs from the provided inputs
        chat_history = ChatHistory()
        parse_chat_history(chat_history, inputs)
        task_inputs = SequentialSkagents._parse_task_inputs(inputs)

        session_id: str
        if "session_id" in inputs and inputs["session_id"]:
            session_id = inputs["session_id"]
        else:
            session_id = str(uuid.uuid4().hex)
        request_id = str(uuid.uuid4().hex)

        # Process and stream back intermediate tasks results
        for task in self.tasks[:-1]:
            try:
                i_response: InvokeResponse = await task.invoke(
                    history=chat_history, inputs=task_inputs
                )
                i_response.session_id = session_id
                i_response.source = f"{self.name}:{self.version}"
                i_response.request_id = request_id

                task_inputs[f"_{task.name}"] = i_response.output_raw
                completion_tokens += i_response.token_usage.completion_tokens
                prompt_tokens += i_response.token_usage.prompt_tokens
                total_tokens += i_response.token_usage.total_tokens
                collector.add_extra_data_items(i_response.extra_data)
                task_no += 1
                yield IntermediateTaskResponse(
                    task_no=task_no,
                    task_name=task.name,
                    response=i_response,
                )
            except Exception as e:
                raise AgentInvokeException(
                    f"Error invoking {self.name}:{self.version} "
                    f"for Session-id {session_id}, Request-id {request_id}, "
                    f"Task description {task.description}. Error: {str(e)}"
                ) from e

        # Process and stream back final task results
        async for chunk in self.tasks[-1].invoke_stream(history=chat_history, inputs=task_inputs):
            # Initialize content as the partial message in chunk
            content = chunk.content
            # Calculate usage metrics if chunk contains usage metadata
            call_usage = get_token_usage_for_response(self.tasks[-1].agent.get_model_type(), chunk)
            completion_tokens += call_usage.completion_tokens
            prompt_tokens += call_usage.prompt_tokens
            total_tokens += call_usage.total_tokens
            try:
                # Attempt to parse as ExtraDataPartial
                extra_data_partial: ExtraDataPartial = ExtraDataPartial.new_from_json(content)
                collector.add_extra_data_items(extra_data_partial.extra_data)
            except Exception:
                # Handle and return partial response
                final_response.append(content)
                yield PartialResponse(
                    session_id=session_id,
                    source=f"{self.name}:{self.version}",
                    request_id=request_id,
                    output_partial=content,
                )
        logger.info(
            f"{self.name}:{self.version} responded with {total_tokens} tokens. "
            f"Session-id {session_id}, Request-id {request_id}"
        )
        # Build the final response with InvokeResponse
        final_response = "".join(final_response)
        response = InvokeResponse(
            session_id=session_id,
            source=f"{self.name}:{self.version}",
            request_id=request_id,
            token_usage=TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            ),
            extra_data=collector.get_extra_data(),
            output_raw=final_response,
        )
        # Format and transform for pydantic output
        if self.config.config.output_type is None:
            yield response
        else:
            yield await self._transform_output_if_required(response)

    async def invoke(self, inputs: dict[str, Any] | None = None) -> InvokeResponse:
        task_no = 0

        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0

        collector = ExtraDataCollector()

        chat_history = ChatHistory()
        parse_chat_history(chat_history, inputs)
        task_inputs = SequentialSkagents._parse_task_inputs(inputs)

        session_id: str
        if "session_id" in inputs and inputs["session_id"]:
            session_id = inputs["session_id"]
        else:
            session_id = str(uuid.uuid4().hex)
        request_id = str(uuid.uuid4().hex)

        for task in self.tasks:
            try:
                i_response = await task.invoke(history=chat_history, inputs=task_inputs)
                task_inputs[f"_{task.name}"] = i_response.output_raw
                completion_tokens += i_response.token_usage.completion_tokens
                prompt_tokens += i_response.token_usage.prompt_tokens
                total_tokens += i_response.token_usage.total_tokens
                collector.add_extra_data_items(i_response.extra_data)
                task_no += 1
            except Exception as e:
                raise AgentInvokeException(
                    f"Error invoking {self.name}:{self.version} "
                    f"for Session-id {session_id}, Request-id {request_id}, "
                    f"Task description {task.description}. Error: {str(e)}"
                ) from e
        logger.info(
            f"{self.name}:{self.version} responded with {total_tokens} tokens. "
            f"Session-id {session_id}, Request-id {request_id}"
        )
        last_message = chat_history.messages[-1].content
        response = InvokeResponse(
            session_id=session_id,
            source=f"{self.name}:{self.version}",
            request_id=request_id,
            token_usage=TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            ),
            extra_data=collector.get_extra_data(),
            output_raw=last_message,
        )
        if self.config.config.output_type is None:
            return response
        else:
            return await self._transform_output_if_required(response)
