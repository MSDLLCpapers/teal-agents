"""Tests for HistoryMultiModalMessage auto-conversion validator."""

import pytest
from pydantic import ValidationError

from sk_agents.ska_types import (
    ContentType,
    HistoryMultiModalMessage,
    MultiModalItem,
)


class TestHistoryMultiModalMessageAutoConversion:
    """Tests for the convert_content_to_items model_validator."""

    def test_plain_content_string_is_converted_to_items(self):
        """Plain HistoryMessage format {role, content}
        should auto-convert to {role, items}."""
        msg = HistoryMultiModalMessage(
            **{"role": "user", "content": "tell me the latest company news"}
        )
        assert len(msg.items) == 1
        assert msg.items[0].content == "tell me the latest company news"
        assert msg.items[0].content_type == ContentType.TEXT

    def test_items_format_passes_through_unchanged(self):
        """Already-correct multimodal format should not be modified."""
        msg = HistoryMultiModalMessage(
            role="assistant",
            items=[MultiModalItem(content_type=ContentType.TEXT, content="hello")],
        )
        assert len(msg.items) == 1
        assert msg.items[0].content == "hello"
        assert msg.items[0].content_type == ContentType.TEXT

    def test_items_with_image_passes_through(self):
        """Multimodal items with image content_type should pass through."""
        msg = HistoryMultiModalMessage(
            role="user",
            items=[
                MultiModalItem(content_type=ContentType.IMAGE, content="base64data"),
                MultiModalItem(content_type=ContentType.TEXT, content="describe this"),
            ],
        )
        assert len(msg.items) == 2
        assert msg.items[0].content_type == ContentType.IMAGE
        assert msg.items[1].content_type == ContentType.TEXT

    def test_content_field_not_present_when_items_provided(self):
        """When items are provided, no extra content field should appear."""
        msg = HistoryMultiModalMessage(
            role="user",
            items=[MultiModalItem(content="test")],
        )
        assert not hasattr(msg, "content") or "content" not in msg.model_fields

    def test_both_content_and_items_prefers_items(self):
        """If both content and items are present, items should take precedence."""
        msg = HistoryMultiModalMessage(
            **{
                "role": "user",
                "content": "ignored",
                "items": [{"content_type": "text", "content": "kept"}],
            }
        )
        assert len(msg.items) == 1
        assert msg.items[0].content == "kept"

    def test_user_role_with_content_conversion(self):
        """User role with content string should convert correctly."""
        msg = HistoryMultiModalMessage(**{"role": "user", "content": "hello"})
        assert msg.role == "user"
        assert msg.items[0].content == "hello"

    def test_assistant_role_with_content_conversion(self):
        """Assistant role with content string should convert correctly."""
        msg = HistoryMultiModalMessage(**{"role": "assistant", "content": "response"})
        assert msg.role == "assistant"
        assert msg.items[0].content == "response"

    def test_empty_content_string_converts(self):
        """Empty content string should still convert to items."""
        msg = HistoryMultiModalMessage(**{"role": "user", "content": ""})
        assert len(msg.items) == 1
        assert msg.items[0].content == ""

    def test_missing_role_raises_validation_error(self):
        """Missing role field should raise a validation error."""
        with pytest.raises(ValidationError):
            HistoryMultiModalMessage(**{"content": "no role"})

    def test_missing_content_and_items_raises_validation_error(self):
        """Missing both content and items should raise a validation error."""
        with pytest.raises(ValidationError):
            HistoryMultiModalMessage(**{"role": "user"})

    def test_items_as_dicts_are_parsed(self):
        """Items provided as raw dicts should be parsed into MultiModalItem."""
        msg = HistoryMultiModalMessage(
            **{
                "role": "user",
                "items": [{"content_type": "text", "content": "from dict"}],
            }
        )
        assert isinstance(msg.items[0], MultiModalItem)
        assert msg.items[0].content == "from dict"
