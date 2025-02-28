from typing import AsyncIterable

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.streaming_chat_message_content import (
    StreamingChatMessageContent,
)

from sk_agents.ska_types import ModelType


class SKAgent:
    def __init__(
        self, model_name: str, model_type: ModelType, agent: ChatCompletionAgent
    ):
        self.model_name = model_name
        self.model_type = model_type
        self.agent = agent

    def get_model_type(self) -> ModelType:
        return self.model_type

    async def invoke_stream(
        self, history: ChatHistory
    ) -> AsyncIterable[StreamingChatMessageContent]:
        async for result in self.agent.invoke_stream(history):
            yield result

    async def invoke(self, history: ChatHistory) -> AsyncIterable[ChatMessageContent]:
        async for result in self.agent.invoke(history):
            yield result
