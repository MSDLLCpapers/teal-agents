import logging

from semantic_kernel.connectors.ai.chat_completion_client_base import ChatCompletionClientBase
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from ska_utils import AppConfig, Config as UtilConfig

from sk_agents.ska_types import ChatCompletionFactory, ModelType

logger = logging.getLogger(__name__)


class OpenAIGpt5Factory(ChatCompletionFactory):
    """Custom factory to expose GPT-5-mini (and 5) to the platform."""

    _OPENAI_MODELS = ["gpt-5-mini", "gpt-5"]

    @staticmethod
    def get_configs() -> list[UtilConfig] | None:
        # No extra env configs needed beyond TA_API_KEY
        return None

    def get_chat_completion_for_model_name(
        self, model_name: str, service_id: str
    ) -> ChatCompletionClientBase:
        if model_name not in self._OPENAI_MODELS:
            raise ValueError("Model type not supported by OpenAIGpt5Factory")
        return OpenAIChatCompletion(
            service_id=service_id,
            ai_model_id=model_name,
            api_key=self.app_config.get("TA_API_KEY"),
        )

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        if model_name in self._OPENAI_MODELS:
            return ModelType.OPENAI
        raise ValueError(f"Unknown model name {model_name}")

    def model_supports_structured_output(self, model_name: str) -> bool:
        if model_name in self._OPENAI_MODELS:
            return True
        raise ValueError(f"Unknown model name {model_name}")
