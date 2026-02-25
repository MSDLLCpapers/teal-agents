from collections.abc import AsyncIterable
from typing import Any

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.streaming_chat_message_content import (
    StreamingChatMessageContent,
)

from sk_agents.ska_types import ModelType
from sk_agents.skagents.v1.utils import get_reasoning_tokens_for_response


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
        self._last_tool_calls: list[str] = []
        self._last_reasoning_tokens: int = 0

    def get_model_type(self) -> ModelType:
        return self.model_attributes["model_type"]

    def so_supported(self) -> bool:
        return self.model_attributes["so_supported"]

    @property
    def last_tool_calls(self) -> list[str]:
        """Return tool call names from the most recent invocation."""
        return list(self._last_tool_calls)

    @property
    def last_reasoning_tokens(self) -> int:
        """Return the reasoning token count from the most recent invocation."""
        return self._last_reasoning_tokens

    @staticmethod
    def _extract_tool_calls_from_history(
        history: ChatHistory, initial_message_count: int
    ) -> list[str]:
        """Extract tool call names from messages added to history during invocation.

        Semantic Kernel's ChatCompletionAgent automatically handles tool calling
        and appends FunctionCallContent items to the chat history. This method
        inspects the new messages added during an invocation to extract tool names.
        """
        tool_calls: list[str] = []
        for message in history.messages[initial_message_count:]:
            for item in message.items:
                if isinstance(item, FunctionCallContent):
                    full_name = (
                        f"{item.plugin_name}.{item.function_name}"
                        if item.plugin_name
                        else item.function_name
                    )
                    tool_calls.append(full_name)
        return tool_calls

    @staticmethod
    def _extract_reasoning_from_history(
        history: ChatHistory, initial_message_count: int
    ) -> int:
        """Extract total reasoning tokens from messages added during invocation."""
        total_reasoning = 0
        for message in history.messages[initial_message_count:]:
            total_reasoning += get_reasoning_tokens_for_response(message)
        return total_reasoning

    async def invoke_stream(
        self, history: ChatHistory
    ) -> AsyncIterable[StreamingChatMessageContent]:
        initial_count = len(history.messages)
        self._last_tool_calls = []
        self._last_reasoning_tokens = 0
        async for result in self.agent.invoke_stream(messages=history):
            yield result.content
        self._last_tool_calls = SKAgent._extract_tool_calls_from_history(
            history, initial_count
        )
        self._last_reasoning_tokens = SKAgent._extract_reasoning_from_history(
            history, initial_count
        )

    async def invoke(self, history: ChatHistory) -> AsyncIterable[ChatMessageContent]:
        initial_count = len(history.messages)
        self._last_tool_calls = []
        self._last_reasoning_tokens = 0
        async for result in self.agent.invoke(messages=history):
            yield result.content
        self._last_tool_calls = SKAgent._extract_tool_calls_from_history(
            history, initial_count
        )
        self._last_reasoning_tokens = SKAgent._extract_reasoning_from_history(
            history, initial_count
        )
