from ska_utils import AppConfig, Config as UtilConfig

from src.sk_agents.ska_types import ChatCompletionFactory, ModelType


class MockChatCompletionFactory(ChatCompletionFactory):
    _OPENAI_MODELS: list[str] = ["gpt-model"]
    _ANTHROPIC_MODELS: list[str] = [
        "claude-model",
    ]
    _GOOGLE_MODELS: list[str] = [
        "gemini-model",
    ]

    TA_BASE_URL = UtilConfig(
        env_name="TA_BASE_URL",
        is_required=False,
        default_value="https://<Your Azure OpenAI Service Endpoint>",
    )
    TA_API_VERSION = UtilConfig(
        env_name="TA_API_VERSION", is_required=False, default_value="Some-Value"
    )

    _CONFIGS: list[UtilConfig] = [TA_BASE_URL, TA_API_VERSION]

    def __init__(self, app_config: AppConfig):
        pass

    def get_configs():
        return MockChatCompletionFactory._CONFIGS

    def get_chat_completion_for_model_name(self, model_name: str, service_id: str):
        if model_name in MockChatCompletionFactory._OPENAI_MODELS:
            return {"service_id": service_id, "ai_model_id": model_name}
        raise ValueError("Model type not supported")

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        if model_name in MockChatCompletionFactory._OPENAI_MODELS:
            return "openai"
        else:
            raise ValueError(f"Unknown model name {model_name}")

    def model_supports_structured_output(self, model_name: str) -> bool:
        if model_name in MockChatCompletionFactory._OPENAI_MODELS:
            return True
        elif model_name in MockChatCompletionFactory._ANTHROPIC_MODELS:
            return False
        elif model_name in MockChatCompletionFactory._GOOGLE_MODELS:
            return False
        else:
            raise ValueError(f"Unknown model name {model_name}")
