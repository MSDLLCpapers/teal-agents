from semantic_kernel.connectors.ai.chat_completion_client_base import (
    ChatCompletionClientBase,
)
from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
from ska_utils import Config as UtilConfig

from sk_agents.configs import TA_API_KEY
from sk_agents.ska_types import ChatCompletionFactory, ModelType


class DefaultChatCompletionFactory(ChatCompletionFactory):
    _OPENAI_MODELS: list[str] = ["gpt-4o", "gpt-4o-mini"]

    @staticmethod
    def get_configs() -> list[UtilConfig] | None:
        return None

    def get_chat_completion_for_model_name(
        self, model_name: str, service_id: str
    ) -> ChatCompletionClientBase:
        if model_name in self._OPENAI_MODELS:
            return OpenAIChatCompletion(
                service_id=service_id,
                ai_model_id=model_name,
                api_key=self.app_config.get(TA_API_KEY.env_name),
            )
        raise ValueError("Model type not supported")

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        if model_name in self._OPENAI_MODELS:
            return ModelType.OPENAI
        else:
            raise ValueError(f"Unknown model name {model_name}")

    def model_supports_structured_output(self, model_name: str) -> bool:
        if model_name in self._OPENAI_MODELS:
            return True
        else:
            raise ValueError(f"Unknown model name {model_name}")
