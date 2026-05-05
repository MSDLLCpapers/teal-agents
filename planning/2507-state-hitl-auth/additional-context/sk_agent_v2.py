import asyncio
from collections.abc import AsyncIterable
from functools import reduce
from typing import Any

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.chat_completion_client_base import (
    ChatCompletionClientBase,
)
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.function_call_content import FunctionCallContent
from semantic_kernel.contents.function_result_content import FunctionResultContent
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

    async def _invoke_function(self, fc_content: FunctionCallContent) -> FunctionResultContent:
        function = self.agent.kernel.get_function(
            fc_content.plugin_name,
            fc_content.function_name,
        )
        function_result = await function(self.agent.kernel, fc_content.to_kernel_arguments())
        function_result_content = FunctionResultContent.from_function_call_content_and_result(
            fc_content, function_result
        )
        return function_result_content

    async def invoke_stream(
        self, history: ChatHistory
    ) -> AsyncIterable[StreamingChatMessageContent]:
        kernel = self.agent.kernel
        arguments = self.agent.arguments
        chat_completion_service, settings = kernel.select_ai_service(
            arguments=arguments, type=ChatCompletionClientBase
        )
        assert isinstance(chat_completion_service, ChatCompletionClientBase)
        all_responses = []
        async for response_list in chat_completion_service.get_streaming_chat_message_contents(
            chat_history=history,
            settings=settings,
            kernel=kernel,
            arguments=arguments,
        ):
            for response in response_list:
                all_responses.append(response)
                if response.content:
                    yield response
        full_completion: StreamingChatMessageContent = reduce(lambda x, y: x + y, all_responses)
        function_calls = [
            item for item in full_completion.items if isinstance(item, FunctionCallContent)
        ]
        history.add_message(message=full_completion)
        if function_calls:
            results = await asyncio.gather(
                *[self._invoke_function(function_call) for function_call in function_calls]
            )
            for result in results:
                history.add_message(result.to_chat_message_content())
            async for response in self.invoke_stream(history):
                yield response

        # async for result in self.agent.invoke_stream(messages=history):
        #     yield result.content

    async def invoke(self, history: ChatHistory) -> AsyncIterable[ChatMessageContent]:
        kernel = self.agent.kernel
        arguments = self.agent.arguments
        chat_completion_service, settings = kernel.select_ai_service(
            arguments=arguments, type=ChatCompletionClientBase
        )
        assert isinstance(chat_completion_service, ChatCompletionClientBase)
        response_list = await chat_completion_service.get_chat_message_contents(
            chat_history=history,
            settings=settings,
            kernel=kernel,
            arguments=arguments,
        )
        function_calls = []
        for response in response_list:
            if (
                response.items
                and response.items[0]
                and isinstance(response.items[0], FunctionCallContent)
            ):
                history.add_message(response)
                function_calls.append(response.items[0])
            else:
                yield response
        if function_calls:
            results = await asyncio.gather(
                *[self._invoke_function(function_call) for function_call in function_calls]
            )
            for result in results:
                history.add_message(result.to_chat_message_content())
            async for response in self.invoke(history):
                yield response
        # async for result in self.agent.invoke(messages=history):
        #     yield result.content
