from collections.abc import AsyncIterable
from typing import Any

from semantic_kernel.contents import ChatMessageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.utils.author_role import AuthorRole

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


class ChatAgents(BaseHandler):
    def __init__(self, config: BaseConfig, agent_builder: AgentBuilder, is_v2: bool = False):
        if not is_v2:
            if config.input_type not in [
                "BaseInput",
                "BaseInputWithUserContext",
                "BaseMultiModalInput",
            ]:
                raise ValueError("Invalid input type")

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

    async def invoke_stream(
        self, inputs: dict[str, Any] | None = None
    ) -> AsyncIterable[PartialResponse | InvokeResponse]:
        extra_data_collector = ExtraDataCollector()
        agent = self.agent_builder.build_agent(self.config.get_agent(), extra_data_collector)

        # Initialize tasks count and token metrics
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0
        final_response = []
        # Initialize and parse the chat history
        chat_history = ChatHistory()
        ChatAgents._augment_with_user_context(inputs=inputs, chat_history=chat_history)
        parse_chat_history(chat_history, inputs)

        # Process the final task with streaming
        async for chunk in agent.invoke_stream(chat_history):
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
                    yield PartialResponse(output_partial=content)
        # Build the final response with InvokeResponse
        final_response = "".join(final_response)
        response = InvokeResponse(
            token_usage=TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            ),
            extra_data=extra_data_collector.get_extra_data(),
            output_raw=final_response,
        )
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
        async for content in agent.invoke(chat_history):
            response_content.append(content)
            call_usage = get_token_usage_for_response(agent.get_model_type(), content)
            completion_tokens += call_usage.completion_tokens
            prompt_tokens += call_usage.prompt_tokens
            total_tokens += call_usage.total_tokens
        return InvokeResponse(
            token_usage=TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            ),
            extra_data=extra_data_collector.get_extra_data(),
            output_raw=response_content[-1].content,
        )
