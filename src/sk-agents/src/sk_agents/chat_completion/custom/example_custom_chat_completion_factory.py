from anthropic import AsyncAnthropic
from semantic_kernel.connectors.ai.anthropic.services.anthropic_chat_completion import (
    AnthropicChatCompletion,
)
from semantic_kernel.connectors.ai.chat_completion_client_base import (
    ChatCompletionClientBase,
)
from semantic_kernel.connectors.ai.google.google_ai.services.google_ai_chat_completion import (
    GoogleAIChatCompletion,
)
from semantic_kernel.connectors.ai.open_ai.services.azure_chat_completion import (
    AzureChatCompletion,
)
from ska_utils import AppConfig, Config as UtilConfig

from sk_agents.configs import TA_API_KEY
from sk_agents.ska_types import ChatCompletionFactory, ModelType


class ExampleCustomChatCompletionFactory(ChatCompletionFactory):
    _OPENAI_MODELS: list[str] = [
        "gpt-35-turbo-1106",
        "gpt-35-turbo-0125",
        "gpt-4o-2024-05-13",
        "gpt-4o-2024-08-06",
        "gpt-4o-mini-2024-07-18",
        "gpt-4-turbo-2024-04-09",
    ]
    _ANTHROPIC_MODELS: list[str] = [
        "claude-3-haiku-20240307-v1",
        "claude-3-sonnet-20240229-v1",
        "claude-3-opus-20240229-v1",
        "claude-3-5-sonnet-20240620-v1",
        "claude-3-5-sonnet-20241022-v2",
        "claude-3-5-haiku-20241022-v1",
        "claude-3-7-sonnet-20250219-v1",
        "claude-opus-4-20250514-v1",
        "claude-opus-4-1-20250805-v1",
        "claude-sonnet-4-20250514-v1",
        "claude-sonnet-4-5-20250929-v1",
        "claude-sonnet-4-6",
        "claude-haiku-4-5-20251001-v1",
        "claude-opus-4-5-20251101-v1",
        "claude-opus-4-6-v1",
    ]

    _GOOGLE_MODELS: list[str] = [
        "gemini-2-5-pro",
        "gemini-2-5-flash",
        "gemini-2-0-flash",
        "gemini-2-0-flash-lite",
        "gemini-embedding-001",
        "gemini-2.5-flash-image",
        "gemini-3-pro-preview",
        "gemini-3-1-pro-preview",
        "gemini-3-pro-image-preview",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-image-preview",
        "gemini-3.1-flash-lite-preview",
    ]

    TA_BASE_URL = UtilConfig(
        env_name="TA_BASE_URL",
        is_required=False,
        default_value="https://<Your AI Service Endpoint>",
    )
    TA_API_VERSION = UtilConfig(
        env_name="TA_API_VERSION", is_required=False, default_value="2024-10-21"
    )

    _CONFIGS: list[UtilConfig] = [TA_BASE_URL, TA_API_VERSION]

    def __init__(self, app_config: AppConfig):
        super().__init__(app_config)
        self.api_key = app_config.get(TA_API_KEY.env_name)
        self.url_base = app_config.get(ExampleCustomChatCompletionFactory.TA_BASE_URL.env_name)
        self.api_version = app_config.get(
            ExampleCustomChatCompletionFactory.TA_API_VERSION.env_name
        )

    @staticmethod
    def get_configs() -> list[UtilConfig]:
        return ExampleCustomChatCompletionFactory._CONFIGS

    def get_chat_completion_for_model_name(
        self, model_name: str, service_id: str
    ) -> ChatCompletionClientBase:
        if model_name in ExampleCustomChatCompletionFactory._OPENAI_MODELS:
            return AzureChatCompletion(
                service_id=service_id,
                deployment_name=model_name,
                api_key=self.api_key,
                base_url=f"{self.url_base}/openai",
                api_version=self.api_version,
            )
        elif model_name in ExampleCustomChatCompletionFactory._ANTHROPIC_MODELS:
            # Use model name as-is for the API path - no modifications
            # This supports both versioned (claude-3-7-sonnet-20250219-v1) 
            # and unversioned (claude-3-haiku) model names flexibly
            return AnthropicChatCompletion(
                service_id=service_id,
                api_key="unused",
                ai_model_id=model_name,
                async_client=AsyncAnthropic(
                    api_key="unused",
                    base_url=f"{self.url_base}/anthropic/{model_name}",
                    default_headers={"api-key": self.api_key},
                ),
            )
        elif model_name in ExampleCustomChatCompletionFactory._GOOGLE_MODELS:
            return GoogleAIChatCompletion(
                service_id=service_id,
                deployment_name=model_name,
                api_key=self.api_key,
            )
        else:
            raise ValueError("Model type not supported")

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        if model_name in ExampleCustomChatCompletionFactory._OPENAI_MODELS:
            return ModelType.OPENAI
        elif model_name in ExampleCustomChatCompletionFactory._ANTHROPIC_MODELS:
            return ModelType.ANTHROPIC
        elif model_name in ExampleCustomChatCompletionFactory._GOOGLE_MODELS:
            return ModelType.GOOGLE
        else:
            raise ValueError(f"Unknown model name {model_name}")

    def model_supports_structured_output(self, model_name: str) -> bool:
        if model_name in ExampleCustomChatCompletionFactory._OPENAI_MODELS:
            return True
        elif model_name in ExampleCustomChatCompletionFactory._ANTHROPIC_MODELS:
            return False
        elif model_name in ExampleCustomChatCompletionFactory._GOOGLE_MODELS:
            return True
        else:
            raise ValueError(f"Unknown model name {model_name}")
