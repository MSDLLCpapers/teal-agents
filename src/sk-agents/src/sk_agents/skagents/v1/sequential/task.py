from collections.abc import AsyncIterable
from typing import Any

from jinja2 import Template
from semantic_kernel.contents import (
    AuthorRole,
    ChatMessageContent,
    ImageContent,
    TextContent,
)
from semantic_kernel.contents.chat_history import ChatHistory
from semantic_kernel.kernel_pydantic import KernelBaseModel

from sk_agents.extra_data_collector import ExtraDataCollector, ExtraDataPartial
from sk_agents.ska_types import EmbeddedImage, InvokeResponse, TokenUsage
from sk_agents.skagents.v1.sk_agent import SKAgent
from sk_agents.skagents.v1.utils import get_token_usage_for_response


class StreamOptions(KernelBaseModel):
    include_usage: bool | None = False


class Task:
    def __init__(
        self,
        name: str,
        description: str,
        instructions: str,
        agent: SKAgent,
        extra_data_collector: ExtraDataCollector | None = None,
    ):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.agent = agent
        self.extra_data_collector = extra_data_collector

    def _get_user_message_with_inputs(self, inputs: dict[str, Any] | None = None) -> str:
        return self.instructions if inputs is None else Template(self.instructions).render(inputs)

    @staticmethod
    def _embedded_image_to_image_content(
        embedded_image: EmbeddedImage | None,
    ) -> ImageContent | None:
        if embedded_image:
            data_uri = f"data:{embedded_image.format};base64,{embedded_image.data}"
            return ImageContent(data_uri=data_uri)
        return None

    @staticmethod
    def _parse_image_input(
        inputs: dict[str, Any] | None = None,
    ) -> EmbeddedImage | None:
        if not inputs:
            return None

        if "embedded_image" in inputs:
            return inputs.pop("embedded_image")
        return None

    def _parse_text_input(self, inputs: dict[str, Any] | None = None) -> TextContent:
        content = self._get_user_message_with_inputs(inputs)
        return TextContent(text=content)

    def _get_message(self, inputs: dict[str, Any] | None = None) -> ChatMessageContent:
        embedded_image = Task._parse_image_input(inputs)
        image_content = Task._embedded_image_to_image_content(embedded_image)
        text_content = self._parse_text_input(inputs)
        return ChatMessageContent(
            role=AuthorRole.USER,
            items=[text_content, image_content] if image_content else [text_content],
        )

    async def invoke_stream(
        self,
        history: ChatHistory,
        inputs: dict[str, Any] | None = None,
    ) -> AsyncIterable[str]:
        # TODO - Need to add capability to retrieve usage stats from the call.
        #  Currently not supported by SK, but there
        #  is an open issue to add this feature: https://github.com/microsoft/semantic-kernel/issues/8996
        #  Details from the OpenAI side can be found at:
        #  https://community.openai.com/t/usage-stats-now-available-when-using-streaming-with-the-chat-completions-api-or-completions-api/738156
        # settings = self.agent.kernel.get_prompt_execution_settings_from_service_id(
        #     self.agent.service_id
        # )
        # settings.stream_options = StreamOptions(include_usage=True).__dict__
        # self.agent.execution_settings = settings

        message = self._get_message(inputs)
        history.add_message(message)
        contents = []
        async for content in self.agent.invoke_stream(history):
            contents.append(content)
            yield content.content
        if not self.extra_data_collector.is_empty():
            yield ExtraDataPartial(
                extra_data=self.extra_data_collector.get_extra_data()
            ).model_dump_json()
        message_content = "".join([content.content for content in contents])
        history.add_assistant_message(message_content)

    async def invoke(
        self,
        history: ChatHistory,
        inputs: dict[str, Any] | None = None,
    ) -> InvokeResponse:
        message = self._get_message(inputs)
        history.add_message(message)
        response_content = []
        completion_tokens: int = 0
        prompt_tokens: int = 0
        total_tokens: int = 0
        async for content in self.agent.invoke(history):
            response_content.append(content)
            history.add_message(content)
            call_usage = get_token_usage_for_response(self.agent.get_model_type(), content)
            completion_tokens += call_usage.completion_tokens
            prompt_tokens += call_usage.prompt_tokens
            total_tokens += call_usage.total_tokens
        return InvokeResponse(
            token_usage=TokenUsage(
                completion_tokens=completion_tokens,
                prompt_tokens=prompt_tokens,
                total_tokens=total_tokens,
            ),
            extra_data=self.extra_data_collector.get_extra_data(),
            output_raw=response_content[-1].content,
        )
