from collections.abc import AsyncIterable
from typing import Any

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.streaming_chat_message_content import (
    StreamingChatMessageContent,
)

from sk_agents.ska_types import ModelType


class SKAgent:
    def __init__(
        self,
        model_name: str,
        model_attributes: dict[str, Any],
        agent: ChatCompletionAgent,
    ):
        self.model_name = model_name
        self.agent = agent
        self.model_attributes = model_attributes

    def get_model_type(self) -> ModelType:
        return self.model_attributes["model_type"]

    def so_supported(self) -> bool:
        return self.model_attributes["so_supported"]

    async def invoke_stream(
        self, history: ChatHistory
    ) -> AsyncIterable[StreamingChatMessageContent]:
        async for result in self.agent.invoke_stream(messages=history):
            yield result.content

    async def invoke(self, history: ChatHistory) -> AsyncIterable[ChatMessageContent]:
        async for result in self.agent.invoke(messages=history):
            yield result.content
