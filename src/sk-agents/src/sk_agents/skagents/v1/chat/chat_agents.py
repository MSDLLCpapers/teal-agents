import logging
import time
import uuid
from collections.abc import AsyncIterable
from typing import Any

from semantic_kernel.contents import ChatMessageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.utils.author_role import AuthorRole
from ska_utils import AgentTelemetryLogger, get_telemetry

from sk_agents.extra_data_collector import ExtraDataCollector, ExtraDataPartial
from sk_agents.ska_types import (
    BaseConfig,
    BaseHandler,
    InvokeResponse,
    PartialResponse,
    TokenUsage,
)
from sk_agents.skagents.v1 import AgentBuilder
from sk_agents.skagents.v1.chat.config import Config
from sk_agents.skagents.v1.utils import (
    get_token_usage_for_response,
    parse_chat_history,
)

logger = logging.getLogger(__name__)


class ChatAgents(BaseHandler):
    def __init__(self, config: BaseConfig, agent_builder: AgentBuilder, is_v2: bool = False):
        self.version = config.version
        if not is_v2:
            self.name = config.service_name
            if config.input_type not in [
                "BaseInput",
                "BaseInputWithUserContext",
                "BaseMultiModalInput",
                "BaseMultiModalInputWithUserContext",
            ]:
                raise ValueError("Invalid input type")
        else:
            self.name = config.name

        if hasattr(config, "spec"):
            self.config = Config(config=config)
        else:
            raise ValueError("Invalid config")

        self.agent_builder = agent_builder

    @staticmethod
    def _augment_with_user_context(
        inputs: dict[str, Any] | None, chat_history: ChatHistory
    ) -> None:
        if "user_context" in inputs and inputs["user_context"]:
            content = "The following user context was provided:\n"
            for key, value in inputs["user_context"].items():
                content += f"  {key}: {value}\n"
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, items=[TextContent(text=content)])
            )

    @staticmethod
    def _extract_user_isid(inputs: dict[str, Any] | None) -> str | None:
        """Extract user ISID from inputs user_context if available."""
        if inputs and "user_context" in inputs and inputs["user_context"]:
            user_context = inputs["user_context"]
            return user_context.get("user.isid") or user_context.get("isid")
        return None

    async def invoke_stream(
        self, inputs: dict[str, Any] | None = None
    ) -> AsyncIterable[PartialResponse | InvokeResponse]:
        jt = get_telemetry()
        extra_data_collector = ExtraDataCollector()
        agent = self.agent_builder.build_agent(self.config.get_agent(), extra_data_collector)

        # Initialize agent telemetry logger with rich metadata
        agent_config = self.config.get_agent()
        user_isid = ChatAgents._extract_user_isid(inputs)
        agent_telemetry = AgentTelemetryLogger(
            agent_name=agent_config.name,
            model_name=agent_config.model,
            user_isid=user_isid,
            telemetry=jt,
        )

        # Initialize tasks count and token metrics
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0
        final_response = []
        # Initialize and parse the chat history
        chat_history = ChatHistory()
        ChatAgents._augment_with_user_context(inputs=inputs, chat_history=chat_history)
        parse_chat_history(chat_history, inputs)

        session_id: str
        if "session_id" in inputs and inputs["session_id"]:
            session_id = inputs["session_id"]
        else:
            session_id = str(uuid.uuid4().hex)
        request_id = str(uuid.uuid4().hex)

        # Process the final task with streaming
        with agent_telemetry.trace_agent_invocation(
            "handler-stream", session_id=session_id, request_id=request_id
        ) as stream_span:
            first_token_received = False
            start_time = time.time()
            titme_to_first_token_ms = 0.0
            logger.info("Beginning processing invoke stream")
            async for chunk in agent.invoke_stream(chat_history):
                if not first_token_received:
                    first_token_time = time.time()
                    titme_to_first_token_ms = (first_token_time - start_time) * 1000
                    first_token_received = True
                # Initialize content as the partial message in chunk
                content = chunk.content
                # Calculate usage metrics
                call_usage = get_token_usage_for_response(agent.get_model_type(), chunk)
                completion_tokens += call_usage.completion_tokens
                prompt_tokens += call_usage.prompt_tokens
                total_tokens += call_usage.total_tokens
                try:
                    # Attempt to parse as ExtraDataPartial
                    extra_data_partial: ExtraDataPartial = ExtraDataPartial.new_from_json(content)
                    extra_data_collector.add_extra_data_items(extra_data_partial.extra_data)
                except Exception:
                    if len(content) > 0:
                        # Handle and return partial response
                        final_response.append(content)
                        yield PartialResponse(
                            session_id=session_id,
                            source=f"{self.name}:{self.version}",
                            request_id=request_id,
                            output_partial=content,
                        )
            # Build the final response with InvokeResponse
            logger.info("Building the final response with InvokeRespons")

            # Record tool calls made by the agent during streaming
            tool_calls = getattr(agent, "last_tool_calls", None)
            if isinstance(tool_calls, list) and tool_calls:
                agent_telemetry.record_tool_calls(tool_calls)

            # Record reasoning tokens from the agent
            reasoning_tokens = getattr(agent, "last_reasoning_tokens", 0)
            if isinstance(reasoning_tokens, int) and reasoning_tokens > 0:
                agent_telemetry.record_reasoning(
                    f"reasoning_tokens={reasoning_tokens}"
                )

            # Enrich span with agent metadata
            agent_telemetry.enrich_span(
                span=stream_span,
                session_id=session_id,
                request_id=request_id,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
                time_to_first_token_ms=titme_to_first_token_ms,
            )

            # Emit standardized structured log
            agent_telemetry.emit_log(
                session_id=session_id,
                request_id=request_id,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            )

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
                extra_data=extra_data_collector.get_extra_data(),
                output_raw=final_response,
            )
            logger.info("Final response complete")
            yield response

    async def invoke(
        self,
        inputs: dict[str, Any] | None = None,
    ) -> InvokeResponse:
        extra_data_collector = ExtraDataCollector()
        agent = self.agent_builder.build_agent(self.config.get_agent(), extra_data_collector)
        chat_history = ChatHistory()
        ChatAgents._augment_with_user_context(inputs=inputs, chat_history=chat_history)
        parse_chat_history(chat_history, inputs)
        response_content = []
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0
        jt = get_telemetry()

        # Initialize agent telemetry logger with rich metadata
        agent_config = self.config.get_agent()
        user_isid = ChatAgents._extract_user_isid(inputs)
        agent_telemetry = AgentTelemetryLogger(
            agent_name=agent_config.name,
            model_name=agent_config.model,
            user_isid=user_isid,
            telemetry=jt,
        )

        session_id: str
        if "session_id" in inputs and inputs["session_id"]:
            session_id = inputs["session_id"]
        else:
            session_id = str(uuid.uuid4().hex)
        request_id = str(uuid.uuid4().hex)

        with agent_telemetry.trace_agent_invocation(
            "handler-invoke", session_id=session_id, request_id=request_id
        ) as invoke_span:
            first_token_received = False
            start_time = time.time()
            titme_to_first_token_ms = 0.0
            logger.info("Beginning processing invoke")

            async for content in agent.invoke(chat_history):
                if not first_token_received:
                    first_token_time = time.time()
                    titme_to_first_token_ms = (first_token_time - start_time) * 1000
                    first_token_received = True
                response_content.append(content)
                call_usage = get_token_usage_for_response(agent.get_model_type(), content)
                completion_tokens += call_usage.completion_tokens
                prompt_tokens += call_usage.prompt_tokens
                total_tokens += call_usage.total_tokens

            logger.info("Building the final response with InvokeRespons")

            # Record tool calls made by the agent during invocation
            tool_calls = getattr(agent, "last_tool_calls", None)
            if isinstance(tool_calls, list) and tool_calls:
                agent_telemetry.record_tool_calls(tool_calls)

            # Record reasoning tokens from the agent
            reasoning_tokens = getattr(agent, "last_reasoning_tokens", 0)
            if isinstance(reasoning_tokens, int) and reasoning_tokens > 0:
                agent_telemetry.record_reasoning(
                    f"reasoning_tokens={reasoning_tokens}"
                )

            # Enrich span with agent metadata
            agent_telemetry.enrich_span(
                span=invoke_span,
                session_id=session_id,
                request_id=request_id,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
                time_to_first_token_ms=titme_to_first_token_ms,
            )

            # Emit standardized structured log
            agent_telemetry.emit_log(
                session_id=session_id,
                request_id=request_id,
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            )

            response = InvokeResponse(
                session_id=session_id,
                source=f"{self.name}:{self.version}",
                request_id=request_id,
                token_usage=TokenUsage(
                    completion_tokens=completion_tokens,
                    prompt_tokens=prompt_tokens,
                    total_tokens=total_tokens,
                ),
                extra_data=extra_data_collector.get_extra_data(),
                output_raw=response_content[-1].content,
            )
            logger.info("Final response complete")
            return response
