"""
Custom Chat Completion Factory for Merck GPT API.

This factory creates MerckChatCompletion instances for the Teal Agents platform,
enabling integration with Merck's internal GPT API endpoint.
"""

import logging
from semantic_kernel.connectors.ai.chat_completion_client_base import (
    ChatCompletionClientBase,
)
from ska_utils import AppConfig
from ska_utils.app_config import Config

from sk_agents.ska_types import ChatCompletionFactory, ModelType
from merck_chat_completion import MerckChatCompletion


logger = logging.getLogger(__name__)


# Configuration keys for Merck API
MERCK_API_KEY = Config(
    env_name="MERCK_API_KEY",
    is_required=True,
    default_value=None
)
MERCK_API_ROOT = Config(
    env_name="MERCK_API_ROOT",
    is_required=False,
    default_value="https://iapi-test.merck.com/gpt/v2"
)


class MerckChatCompletionFactory(ChatCompletionFactory):
    """
    Factory for creating Merck GPT API chat completion clients.
    
    This factory extends the ChatCompletionFactory abstract class and provides
    MerckChatCompletion instances configured with Merck's API credentials.
    """

    # Supported Merck models
    _MERCK_MODELS: list[str] = [
        "gpt-5-2025-08-07",
        "gpt-4o",
        "gpt-4o-mini",
    ]

    @staticmethod
    def get_configs() -> list[Config] | None:
        """
        Return configuration requirements for this factory.
        
        Returns:
            List of required Config objects
        """
        return [MERCK_API_KEY, MERCK_API_ROOT]

    def get_chat_completion_for_model_name(
        self, model_name: str, service_id: str
    ) -> ChatCompletionClientBase:
        """
        Create a chat completion client for the specified model.

        Args:
            model_name: The model identifier (e.g., 'gpt-5-2025-08-07')
            service_id: Unique identifier for this service instance

        Returns:
            A configured MerckChatCompletion client

        Raises:
            ValueError: If the model is not supported
        """
        if model_name not in self._MERCK_MODELS:
            raise ValueError(
                f"Model '{model_name}' not supported. "
                f"Supported models: {', '.join(self._MERCK_MODELS)}"
            )

        api_key = self.app_config.get(MERCK_API_KEY.env_name)
        api_root = self.app_config.get(MERCK_API_ROOT.env_name)

        if not api_key:
            raise ValueError("MERCK_API_KEY not configured")

        logger.info(f"Creating MerckChatCompletion client for model: {model_name}")

        return MerckChatCompletion(
            service_id=service_id,
            api_key=api_key,
            api_root=api_root,
            model_name=model_name,
        )

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        """
        Get the model type for the specified model name.

        Args:
            model_name: The model identifier

        Returns:
            ModelType.OPENAI (Merck API follows OpenAI-compatible format)

        Raises:
            ValueError: If the model is not supported
        """
        if model_name in self._MERCK_MODELS:
            # Return OPENAI type as Merck API is OpenAI-compatible
            return ModelType.OPENAI
        else:
            raise ValueError(f"Unknown model name: {model_name}")

    def model_supports_structured_output(self, model_name: str) -> bool:
        """
        Check if the model supports structured output.

        Args:
            model_name: The model identifier

        Returns:
            True if structured output is supported, False otherwise

        Raises:
            ValueError: If the model is not supported
        """
        if model_name in self._MERCK_MODELS:
            # Most GPT models support structured output
            return True
        else:
            raise ValueError(f"Unknown model name: {model_name}")
