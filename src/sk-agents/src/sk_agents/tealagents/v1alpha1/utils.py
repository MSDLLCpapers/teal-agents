from typing import Any

from semantic_kernel.contents import (
    ChatMessageContent,
    ImageContent,
    TextContent
)

from semantic_kernel.contents.chat_history import ChatHistory

from sk_agents.ska_types import (
    ContentType,
    ModelType,
    MultiModalItem,
    TokenUsage,
)


def item_to_content(item: MultiModalItem) -> TextContent | ImageContent:
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
    if (
        inputs is not None
        and "chat_history" in inputs
        and inputs["chat_history"] is not None
    ):
        for message in inputs["chat_history"]:
            if hasattr(message, "content"):
                items = [
                    MultiModalItem(
                        content_type=ContentType.TEXT,
                        content=message.content
                    )
                ]
            elif hasattr(message, "items"):
                items = message.items
            else:
                return chat_history

            chat_message_items: list[TextContent | ImageContent] = []
            for item in items:
                chat_message_items.append(item_to_content(item))
            message_content = ChatMessageContent(
                role=message.role,
                items=chat_message_items
            )
            chat_history.add_message(message_content)
    return chat_history


def get_token_usage_for_response(
        model_type: ModelType,
        content: ChatMessageContent
) -> TokenUsage:
    # Check if the content is a ChatMessageContent object 
    # and if it contains usage information
    if (
        isinstance(content, ChatMessageContent)
        and hasattr(content.inner_content, "usage")
        and content.inner_content.usage is not None
    ):
        if model_type == ModelType.OPENAI:
            return get_token_usage_for_openai_response(content)
        elif model_type == ModelType.ANTHROPIC:
            return get_token_usage_for_anthropic_response(content)
    return TokenUsage(
        completion_tokens=0,
        prompt_tokens=0,
        total_tokens=0
    )


def get_token_usage_for_openai_response(
        content: ChatMessageContent
) -> TokenUsage:
    completion_tokens = content.inner_content.usage.completion_tokens
    prompt_tokens = content.inner_content.usage.prompt_tokens
    total_tokens = completion_tokens + prompt_tokens
    return TokenUsage(
        completion_tokens=completion_tokens,
        prompt_tokens=prompt_tokens,
        total_tokens=total_tokens,
    )


def get_token_usage_for_anthropic_response(
    content: ChatMessageContent,
) -> TokenUsage:
    output_tokens = content.inner_content.usage.output_tokens
    input_tokens = content.inner_content.usage.input_tokens
    total_tokens = output_tokens + input_tokens
    return TokenUsage(
        completion_tokens=output_tokens,
        prompt_tokens=input_tokens,
        total_tokens=total_tokens,
    )
