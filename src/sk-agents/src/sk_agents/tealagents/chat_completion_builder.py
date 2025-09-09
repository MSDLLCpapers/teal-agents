import logging

from semantic_kernel.connectors.ai.chat_completion_client_base import (
    ChatCompletionClientBase,
)
from ska_utils import AppConfig, ModuleLoader

from sk_agents.chat_completion.default_chat_completion_factory import (
    DefaultChatCompletionFactory,
)
from sk_agents.configs import (
    TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME,
    TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE,
)
from sk_agents.ska_types import ChatCompletionFactory, ModelType


class ChatCompletionBuilder:
    def __init__(self, app_config: AppConfig):
        self.logger = logging.getLogger(__name__)
        self.app_config = app_config

        cccf_module_name = self.app_config.get(TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE.env_name)
        if cccf_module_name:
            ccc_factory_name = self.app_config.get(
                TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME.env_name
            )
            if not ccc_factory_name:
                raise ValueError("Custom Chat Completion Factory class name not provided")

            cccf_module = ModuleLoader.load_module(cccf_module_name)
            if not hasattr(cccf_module, ccc_factory_name):
                raise ValueError(
                    f"Custom Chat Completion Factory class: {ccc_factory_name}"
                    f"Not found in module: {cccf_module_name}"
                )
            ccc_factory_type: type[ChatCompletionFactory] = getattr(cccf_module, ccc_factory_name)
            ccc_factory_configs = ccc_factory_type.get_configs()
            if ccc_factory_configs:
                AppConfig.add_configs(ccc_factory_configs)
            self.ccc_factory: ChatCompletionFactory | None = ccc_factory_type(app_config)
        else:
            self.ccc_factory = None
        self.self_default_cc_factory = DefaultChatCompletionFactory(app_config)

    def get_chat_completion_for_model(
        self,
        service_id: str,
        model_name: str,
    ) -> ChatCompletionClientBase:
        if self.ccc_factory:
            try:
                return self.ccc_factory.get_chat_completion_for_model_name(model_name, service_id)
            except ValueError:
                self.logger.warning(f"Could not find model {model_name} using custom factory")
        return self.self_default_cc_factory.get_chat_completion_for_model_name(
            model_name, service_id
        )

    def get_model_type_for_name(self, model_name: str) -> ModelType:
        if self.ccc_factory:
            try:
                return self.ccc_factory.get_model_type_for_name(model_name)
            except ValueError:
                self.logger.warning(f"Could not find model {model_name} using custom factory")
        return self.self_default_cc_factory.get_model_type_for_name(model_name)

    def model_supports_structured_output(self, model_name: str) -> bool:
        if self.ccc_factory:
            try:
                return self.ccc_factory.model_supports_structured_output(model_name)
            except ValueError:
                self.logger.warning(f"Could not find model {model_name} using custom factory")
        return self.self_default_cc_factory.model_supports_structured_output(model_name)
