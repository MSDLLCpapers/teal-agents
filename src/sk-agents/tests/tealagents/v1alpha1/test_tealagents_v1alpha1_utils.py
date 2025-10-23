from unittest.mock import MagicMock

from semantic_kernel.contents import ChatMessageContent, ImageContent, TextContent
from semantic_kernel.contents.chat_history import ChatHistory

from sk_agents.ska_types import ContentType, ModelType, MultiModalItem, TokenUsage
from sk_agents.tealagents.v1alpha1.utils import (
    get_token_usage_for_anthropic_response,
    get_token_usage_for_openai_response,
    get_token_usage_for_response,
    item_to_content,
    parse_chat_history,
)


class TestItemToContent:
    """Test item_to_content function."""

    def test_item_to_content_text(self):
        """Test converting TEXT content type to TextContent."""
        item = MultiModalItem(content_type=ContentType.TEXT, content="Hello, world!")

        result = item_to_content(item)

        assert isinstance(result, TextContent)
        assert result.text == "Hello, world!"

    def test_item_to_content_image(self):
        """Test converting IMAGE content type to ImageContent."""
        # Valid base64 encoded 1x1 transparent PNG
        data_uri = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
            "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )
        item = MultiModalItem(content_type=ContentType.IMAGE, content=data_uri)

        result = item_to_content(item)

        assert isinstance(result, ImageContent)
        assert result.data_uri == data_uri

    def test_item_to_content_unknown(self):
        """Test that unknown content type returns None."""
        # Create a mock item with an invalid content_type
        item = MagicMock()
        item.content_type = "invalid_type"
        item.content = "some content"

        result = item_to_content(item)

        assert result is None


class TestParseChatHistory:
    """Test parse_chat_history function."""

    def test_parse_chat_history_with_none_inputs(self):
        """Test parse_chat_history with None inputs."""
        chat_history = ChatHistory()

        result = parse_chat_history(chat_history, inputs=None)

        assert result is chat_history
        assert len(result.messages) == 0

    def test_parse_chat_history_with_empty_inputs(self):
        """Test parse_chat_history with empty inputs dict."""
        chat_history = ChatHistory()

        result = parse_chat_history(chat_history, inputs={})

        assert result is chat_history
        assert len(result.messages) == 0

    def test_parse_chat_history_with_no_chat_history_key(self):
        """Test parse_chat_history when inputs has no 'chat_history' key."""
        chat_history = ChatHistory()

        result = parse_chat_history(chat_history, inputs={"other_key": "value"})

        assert result is chat_history
        assert len(result.messages) == 0

    def test_parse_chat_history_with_none_chat_history_value(self):
        """Test parse_chat_history when chat_history value is None."""
        chat_history = ChatHistory()

        result = parse_chat_history(chat_history, inputs={"chat_history": None})

        assert result is chat_history
        assert len(result.messages) == 0

    def test_parse_chat_history_with_content_attribute(self):
        """Test parse_chat_history with messages that have content attribute."""
        chat_history = ChatHistory()

        # Create mock message with content attribute
        message = MagicMock()
        message.role = "user"
        message.content = "Hello, assistant!"
        delattr(message, "items")  # Ensure items doesn't exist

        inputs = {"chat_history": [message]}

        result = parse_chat_history(chat_history, inputs=inputs)

        assert len(result.messages) == 1
        assert result.messages[0].role == "user"
        assert len(result.messages[0].items) == 1
        assert isinstance(result.messages[0].items[0], TextContent)
        assert result.messages[0].items[0].text == "Hello, assistant!"

    def test_parse_chat_history_with_items_attribute(self):
        """Test parse_chat_history with messages that have items attribute."""
        chat_history = ChatHistory()

        # Valid base64 encoded 1x1 transparent PNG
        valid_base64_image = (
            "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJ"
            "AAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        )

        # Create mock message with items attribute
        message = MagicMock()
        message.role = "assistant"
        delattr(message, "content")  # Ensure content doesn't exist
        message.items = [
            MultiModalItem(content_type=ContentType.TEXT, content="Response text"),
            MultiModalItem(content_type=ContentType.IMAGE, content=valid_base64_image),
        ]

        inputs = {"chat_history": [message]}

        result = parse_chat_history(chat_history, inputs=inputs)

        assert len(result.messages) == 1
        assert result.messages[0].role == "assistant"
        assert len(result.messages[0].items) == 2
        assert isinstance(result.messages[0].items[0], TextContent)
        assert result.messages[0].items[0].text == "Response text"
        assert isinstance(result.messages[0].items[1], ImageContent)

    def test_parse_chat_history_with_multiple_messages(self):
        """Test parse_chat_history with multiple messages."""
        chat_history = ChatHistory()

        # Create multiple messages
        message1 = MagicMock()
        message1.role = "user"
        message1.content = "First message"
        delattr(message1, "items")

        message2 = MagicMock()
        message2.role = "assistant"
        message2.content = "Second message"
        delattr(message2, "items")

        inputs = {"chat_history": [message1, message2]}

        result = parse_chat_history(chat_history, inputs=inputs)

        assert len(result.messages) == 2
        assert result.messages[0].role == "user"
        assert result.messages[1].role == "assistant"

    def test_parse_chat_history_with_invalid_message(self):
        """Test parse_chat_history with message that has neither content nor items."""
        chat_history = ChatHistory()

        # Create message without content or items attributes
        message = MagicMock()
        message.role = "user"
        delattr(message, "content")
        delattr(message, "items")

        inputs = {"chat_history": [message]}

        result = parse_chat_history(chat_history, inputs=inputs)

        # Should return original chat_history without modification
        assert result is chat_history
        assert len(result.messages) == 0


class TestGetTokenUsageForResponse:
    """Test get_token_usage_for_response function."""

    def test_get_token_usage_for_openai_response(self):
        """Test token usage extraction for OpenAI responses."""
        # Create mock ChatMessageContent with usage info
        content = MagicMock(spec=ChatMessageContent)
        content.inner_content = MagicMock()
        content.inner_content.usage = MagicMock()
        content.inner_content.usage.completion_tokens = 100
        content.inner_content.usage.prompt_tokens = 50

        result = get_token_usage_for_response(ModelType.OPENAI, content)

        assert isinstance(result, TokenUsage)
        assert result.completion_tokens == 100
        assert result.prompt_tokens == 50
        assert result.total_tokens == 150

    def test_get_token_usage_for_anthropic_response(self):
        """Test token usage extraction for Anthropic responses."""
        content = MagicMock(spec=ChatMessageContent)
        content.inner_content = MagicMock()
        content.inner_content.usage = MagicMock()
        content.inner_content.usage.output_tokens = 200
        content.inner_content.usage.input_tokens = 75

        result = get_token_usage_for_response(ModelType.ANTHROPIC, content)

        assert isinstance(result, TokenUsage)
        assert result.completion_tokens == 200
        assert result.prompt_tokens == 75
        assert result.total_tokens == 275

    def test_get_token_usage_for_google_response(self):
        """Test token usage for Google returns zero (not supported in v1alpha1)."""
        content = MagicMock(spec=ChatMessageContent)
        content.inner_content = MagicMock()
        content.inner_content.usage = MagicMock()
        content.inner_content.usage.output_tokens = 150
        content.inner_content.usage.input_tokens = 60

        result = get_token_usage_for_response(ModelType.GOOGLE, content)

        # Google not explicitly handled in v1alpha1, should return zeros
        assert isinstance(result, TokenUsage)
        assert result.completion_tokens == 0
        assert result.prompt_tokens == 0
        assert result.total_tokens == 0

    def test_get_token_usage_with_no_inner_content_usage(self):
        """Test token usage when inner_content has no usage attribute."""
        content = MagicMock(spec=ChatMessageContent)
        content.inner_content = MagicMock()
        delattr(content.inner_content, "usage")

        result = get_token_usage_for_response(ModelType.OPENAI, content)

        assert isinstance(result, TokenUsage)
        assert result.completion_tokens == 0
        assert result.prompt_tokens == 0
        assert result.total_tokens == 0

    def test_get_token_usage_with_none_usage(self):
        """Test token usage when usage is None."""
        content = MagicMock(spec=ChatMessageContent)
        content.inner_content = MagicMock()
        content.inner_content.usage = None

        result = get_token_usage_for_response(ModelType.OPENAI, content)

        assert isinstance(result, TokenUsage)
        assert result.completion_tokens == 0
        assert result.prompt_tokens == 0
        assert result.total_tokens == 0

    def test_get_token_usage_with_non_chatmessagecontent(self):
        """Test token usage with non-ChatMessageContent object."""
        content = "not a ChatMessageContent"

        result = get_token_usage_for_response(ModelType.OPENAI, content)

        assert isinstance(result, TokenUsage)
        assert result.completion_tokens == 0
        assert result.prompt_tokens == 0
        assert result.total_tokens == 0


class TestGetTokenUsageForOpenAIResponse:
    """Test get_token_usage_for_openai_response function."""

    def test_get_token_usage_for_openai_response(self):
        """Test OpenAI token usage calculation."""
        content = MagicMock(spec=ChatMessageContent)
        content.inner_content = MagicMock()
        content.inner_content.usage = MagicMock()
        content.inner_content.usage.completion_tokens = 250
        content.inner_content.usage.prompt_tokens = 125

        result = get_token_usage_for_openai_response(content)

        assert result.completion_tokens == 250
        assert result.prompt_tokens == 125
        assert result.total_tokens == 375


class TestGetTokenUsageForAnthropicResponse:
    """Test get_token_usage_for_anthropic_response function."""

    def test_get_token_usage_for_anthropic_response(self):
        """Test Anthropic token usage calculation."""
        content = MagicMock(spec=ChatMessageContent)
        content.inner_content = MagicMock()
        content.inner_content.usage = MagicMock()
        content.inner_content.usage.output_tokens = 300
        content.inner_content.usage.input_tokens = 150

        result = get_token_usage_for_anthropic_response(content)

        assert result.completion_tokens == 300
        assert result.prompt_tokens == 150
        assert result.total_tokens == 450
