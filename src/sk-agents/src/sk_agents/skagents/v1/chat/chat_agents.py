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
    TokenUsage,
)
from sk_agents.skagents.v1 import AgentBuilder
from sk_agents.skagents.v1.chat.config import Config
from sk_agents.skagents.v1.utils import (
    get_token_usage_for_response,
    parse_chat_history,
)


class ChatAgents(BaseHandler):
    def __init__(self, config: BaseConfig, agent_builder: AgentBuilder):
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
        if hasattr(inputs, "user_context"):
            content = "The following user context was provided:\n"
            for key, value in inputs["user_context"].items():
                content += f"  {key}: {value}\n"
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, items=[TextContent(text=content)])
            )

    async def invoke_stream(self, inputs: dict[str, Any] | None = None) -> AsyncIterable[str]:
        extra_data_collector = ExtraDataCollector()
        agent = self.agent_builder.build_agent(self.config.get_agent(), extra_data_collector)

        chat_history = ChatHistory()
        ChatAgents._augment_with_user_context(inputs=inputs, chat_history=chat_history)
        parse_chat_history(chat_history, inputs)
        async for content in agent.invoke_stream(chat_history):
            yield content.content
        if not extra_data_collector.is_empty():
            yield ExtraDataPartial(
                extra_data=extra_data_collector.get_extra_data()
            ).model_dump_json()

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
