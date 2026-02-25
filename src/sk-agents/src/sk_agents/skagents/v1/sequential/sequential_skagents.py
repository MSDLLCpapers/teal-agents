import json
import logging
import time
import uuid
from collections.abc import AsyncIterable
from copy import deepcopy
from typing import Any

from semantic_kernel.contents.chat_history import ChatHistory
from ska_utils import AgentTelemetryLogger, get_telemetry

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

    @staticmethod
    def _extract_user_isid(inputs: dict[str, Any] | None) -> str | None:
        """Extract user ISID from inputs user_context if available."""
        if inputs and "user_context" in inputs and inputs["user_context"]:
            user_context = inputs["user_context"]
            return user_context.get("user.isid") or user_context.get("isid")
        return None

    async def invoke_stream(
        self, inputs: dict[str, Any] | None = None
    ) -> AsyncIterable[PartialResponse | IntermediateTaskResponse | InvokeResponse]:
        collector = ExtraDataCollector()
        jt = get_telemetry()
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

        # Determine agent info from the last task's agent for telemetry
        last_agent_config = None
        agents = self.config.get_agents()
        if agents:
            last_agent_config = agents[-1]

        user_isid = SequentialSkagents._extract_user_isid(inputs)
        agent_telemetry = AgentTelemetryLogger(
            agent_name=last_agent_config.name if last_agent_config else self.name,
            model_name=last_agent_config.model if last_agent_config else "unknown",
            user_isid=user_isid,
            telemetry=jt,
        )

        average_ttft_ms = []
        with agent_telemetry.trace_agent_invocation(
            "handler-stream", session_id=session_id, request_id=request_id
        ) as stream_span:
            logger.info("Beginning processing invoke stream")

            # Process and stream back intermediate tasks results
            for task in self.tasks[:-1]:
                try:
                    logger.info("Creating IntermediateTaskResponse")
                    first_token_received = False
                    start_time = time.time()
                    i_response: InvokeResponse = await task.invoke(
                        history=chat_history, inputs=task_inputs
                    )
                    if not first_token_received:
                        first_token_time = time.time()
                        ttft_ms = (first_token_time - start_time) * 1000
                        average_ttft_ms.append(ttft_ms)
                        first_token_received = True
                    i_response.session_id = session_id
                    i_response.source = f"{self.name}:{self.version}"
                    i_response.request_id = request_id

                    task_inputs[f"_{task.name}"] = i_response.output_raw
                    completion_tokens += i_response.token_usage.completion_tokens
                    prompt_tokens += i_response.token_usage.prompt_tokens
                    total_tokens += i_response.token_usage.total_tokens
                    collector.add_extra_data_items(i_response.extra_data)
                    task_no += 1

                    # Record tool calls made by the agent during this task
                    tool_calls = getattr(task.agent, "last_tool_calls", None)
                    if isinstance(tool_calls, list) and tool_calls:
                        agent_telemetry.record_tool_calls(tool_calls)

                    # Record reasoning tokens from this task
                    reasoning_tokens = getattr(task.agent, "last_reasoning_tokens", 0)
                    if isinstance(reasoning_tokens, int) and reasoning_tokens > 0:
                        agent_telemetry.record_reasoning(
                            f"reasoning_tokens={reasoning_tokens}"
                        )

                    # Record each intermediate task invocation
                    agent_telemetry.record_internal_function_call(
                        f"task:{task.name}"
                    )

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
            logger.info("Beginning final processing")
            # Process and stream back final task results
            first_token_received = False
            start_time = time.time()
            async for chunk in self.tasks[-1].invoke_stream(
                history=chat_history, inputs=task_inputs
            ):
                if not first_token_received:
                    first_token_time = time.time()
                    ttft_ms = (first_token_time - start_time) * 1000
                    average_ttft_ms.append(ttft_ms)
                    first_token_received = True
                # Initialize content as the partial message in chunk
                content = chunk.content
                # Calculate usage metrics if chunk contains usage metadata
                call_usage = get_token_usage_for_response(
                    self.tasks[-1].agent.get_model_type(), chunk
                )
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

            average_ttft = sum(average_ttft_ms) / len(average_ttft_ms) if average_ttft_ms else 0

            # Record tool calls made by the final task's agent
            final_tool_calls = getattr(self.tasks[-1].agent, "last_tool_calls", None)
            if isinstance(final_tool_calls, list) and final_tool_calls:
                agent_telemetry.record_tool_calls(final_tool_calls)

            # Record reasoning tokens from the final task
            final_reasoning = getattr(self.tasks[-1].agent, "last_reasoning_tokens", 0)
            if isinstance(final_reasoning, int) and final_reasoning > 0:
                agent_telemetry.record_reasoning(
                    f"reasoning_tokens={final_reasoning}"
                )

            # Enrich span with agent metadata
            agent_telemetry.enrich_span(
                span=stream_span,
                session_id=session_id,
                request_id=request_id,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
                time_to_first_token_ms=average_ttft,
            )

            # Emit standardized structured log
            agent_telemetry.emit_log(
                session_id=session_id,
                request_id=request_id,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            )

            logger.info(
                f"{self.name}:{self.version} responded with {total_tokens} tokens. "
                f"Session-id {session_id}, Request-id {request_id}"
            )
            logger.info("Building the final response with InvokeResponse")
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
            logger.info("Final response complete")
            # Format and transform for pydantic output
            if self.config.config.output_type is None:
                yield response
            else:
                yield await self._transform_output_if_required(response)

    async def invoke(self, inputs: dict[str, Any] | None = None) -> InvokeResponse:
        jt = get_telemetry()
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

        # Determine agent info from the last task's agent for telemetry
        last_agent_config = None
        agents = self.config.get_agents()
        if agents:
            last_agent_config = agents[-1]

        user_isid = SequentialSkagents._extract_user_isid(inputs)
        agent_telemetry = AgentTelemetryLogger(
            agent_name=last_agent_config.name if last_agent_config else self.name,
            model_name=last_agent_config.model if last_agent_config else "unknown",
            user_isid=user_isid,
            telemetry=jt,
        )

        with agent_telemetry.trace_agent_invocation(
            "handler-invoke", session_id=session_id, request_id=request_id
        ) as invoke_span:
            average_ttft_ms = []
            logger.info("Beginning processing invoke")
            for task in self.tasks:
                try:
                    start_time = time.time()
                    i_response = await task.invoke(history=chat_history, inputs=task_inputs)
                    response_time = time.time()
                    ttft_ms = (response_time - start_time) * 1000
                    average_ttft_ms.append(ttft_ms)
                    task_inputs[f"_{task.name}"] = i_response.output_raw
                    completion_tokens += i_response.token_usage.completion_tokens
                    prompt_tokens += i_response.token_usage.prompt_tokens
                    total_tokens += i_response.token_usage.total_tokens
                    collector.add_extra_data_items(i_response.extra_data)
                    task_no += 1

                    # Record tool calls made by the agent during this task
                    tool_calls = getattr(task.agent, "last_tool_calls", None)
                    if isinstance(tool_calls, list) and tool_calls:
                        agent_telemetry.record_tool_calls(tool_calls)

                    # Record reasoning tokens from this task
                    reasoning_tokens = getattr(task.agent, "last_reasoning_tokens", 0)
                    if isinstance(reasoning_tokens, int) and reasoning_tokens > 0:
                        agent_telemetry.record_reasoning(
                            f"reasoning_tokens={reasoning_tokens}"
                        )

                    # Record each task invocation
                    agent_telemetry.record_internal_function_call(
                        f"task:{task.name}"
                    )
                except Exception as e:
                    raise AgentInvokeException(
                        f"Error invoking {self.name}:{self.version} "
                        f"for Session-id {session_id}, Request-id {request_id}, "
                        f"Task description {task.description}. Error: {str(e)}"
                    ) from e

            average_response_time = (
                sum(average_ttft_ms) / len(average_ttft_ms) if average_ttft_ms else 0
            )

            # Enrich span with agent metadata
            agent_telemetry.enrich_span(
                span=invoke_span,
                session_id=session_id,
                request_id=request_id,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
                time_to_first_token_ms=average_response_time,
            )

            # Emit standardized structured log
            agent_telemetry.emit_log(
                session_id=session_id,
                request_id=request_id,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            )

            logger.info(
                f"{self.name}:{self.version} responded with {total_tokens} tokens. "
                f"Session-id {session_id}, Request-id {request_id}"
            )
            logger.info("Building the final response with InvokeResponse")
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
            logger.info("Final response complete")
            if self.config.config.output_type is None:
                return response
            else:
                return await self._transform_output_if_required(response)
