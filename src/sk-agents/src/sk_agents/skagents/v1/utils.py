from typing import Any

from semantic_kernel.contents import ChatMessageContent, ImageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory

from sk_agents.ska_types import (
    ContentType,
    ModelType,
    MultiModalItem,
    TokenUsage,
)


def item_to_content(item: MultiModalItem) -> TextContent | ImageContent | None:
    match item.content_type:
        case ContentType.TEXT:
            return TextContent(text=item.content)
        case ContentType.IMAGE:
            return ImageContent(data_uri=item.content)
        case _:
            return None


def parse_chat_history(
    chat_history: ChatHistory, inputs: dict[str, Any] | None = None
) -> ChatHistory:
    if inputs is not None and "chat_history" in inputs and inputs["chat_history"] is not None:
        for message in inputs["chat_history"]:
            if hasattr(message, "content"):
                items = [MultiModalItem(content_type=ContentType.TEXT, content=message.content)]
            elif hasattr(message, "items"):
                items = message.items
            else:
                return chat_history

            chat_message_items: list[TextContent | ImageContent] = []
            for item in items:
                chat_message_items.append(item_to_content(item))
            message_content = ChatMessageContent(role=message.role, items=chat_message_items)
            chat_history.add_message(message_content)
    return chat_history


def get_token_usage_for_response(model_type: ModelType, content: ChatMessageContent) -> TokenUsage:
    if model_type == ModelType.OPENAI:
        return get_token_usage_for_openai_response(content)
    elif model_type == ModelType.ANTHROPIC:
        return get_token_usage_for_anthropic_response(content)
    else:
        return TokenUsage(completion_tokens=0, prompt_tokens=0, total_tokens=0)


def get_token_usage_for_openai_response(content: ChatMessageContent) -> TokenUsage:
    return TokenUsage(
        completion_tokens=content.inner_content.usage.completion_tokens,
        prompt_tokens=content.inner_content.usage.prompt_tokens,
        total_tokens=(
            content.inner_content.usage.completion_tokens
            + content.inner_content.usage.prompt_tokens
        ),
    )


def get_token_usage_for_anthropic_response(
    content: ChatMessageContent,
) -> TokenUsage:
    return TokenUsage(
        completion_tokens=content.inner_content.usage.output_tokens,
        prompt_tokens=content.inner_content.usage.input_tokens,
        total_tokens=(
            content.inner_content.usage.output_tokens + content.inner_content.usage.input_tokens
        ),
    )
