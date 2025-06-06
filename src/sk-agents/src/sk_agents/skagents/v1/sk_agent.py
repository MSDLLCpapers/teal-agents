from collections.abc import AsyncIterable
from typing import Any

from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.streaming_chat_message_content import (
    StreamingChatMessageContent,
)

from sk_agents.ska_types import ModelType

from semantic_kernel.services.ai_service_client_base import AIServiceClientBase
from semantic_kernel.connectors.ai.open_ai.prompt_execution_settings.azure_chat_prompt_execution_settings import (
    AzureChatPromptExecutionSettings,
)
from semantic_kernel.functions.kernel_arguments import KernelArguments

from semantic_kernel.connectors.ai.open_ai.services.azure_chat_completion import (
    AzureChatCompletion,
)


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
        service: AzureChatCompletion = self.agent.kernel.get_service(
            service_id="default"
        )
        settings: AzureChatPromptExecutionSettings = (
            service.get_prompt_execution_settings_class()(service_id="default")
        )
        settings.extra_body = {
            "stream_options": {
                "include_usage": True,
            }
        }
        async for chunk in service.get_streaming_chat_message_contents(
            chat_history=history,
            settings=settings,
            kernel=self.agent.kernel,
            arguments=KernelArguments(settings=settings),
        ):
            print(chunk[0].metadata["usage"])
            yield chunk[0]
        # async for result in self.agent.invoke_stream(messages=history):
        #     yield result.content

    async def invoke(self, history: ChatHistory) -> AsyncIterable[ChatMessageContent]:
        async for result in self.agent.invoke(messages=history):
            yield result.content
