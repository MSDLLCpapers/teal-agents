from ska_utils import AppConfig, ModuleLoader, strtobool

from configs import (
    TA_CUSTOM_USER_CONTEXT_CLASS_NAME,
    TA_CUSTOM_USER_CONTEXT_ENABLED,
    TA_CUSTOM_USER_CONTEXT_MODULE,
)
from user_context.in_memory_context import UserContextCache


class CustomUserContextHelper:
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.custom_user_context_enabled = strtobool(
            app_config.get(TA_CUSTOM_USER_CONTEXT_ENABLED.env_name)
        )
        if self.custom_user_context_enabled:
            module_name, class_name = self._get_custom_user_context_config()
            self.module = ModuleLoader.load_module(module_name)

    def get_user_context(self) -> UserContextCache | None:
        if not self.custom_user_context_enabled:
            return None

        class_name = self.app_config.get(TA_CUSTOM_USER_CONTEXT_CLASS_NAME.env_name)
        return getattr(self.module, class_name)()

    def _get_custom_user_context_config(self) -> tuple[str, str]:
        custom_auth_module = self.app_config.get(TA_CUSTOM_USER_CONTEXT_MODULE.env_name)
        if not custom_auth_module:
            raise ValueError("Custom user context module is enabled but not defined")

        custom_authenticator = self.app_config.get(TA_CUSTOM_USER_CONTEXT_CLASS_NAME.env_name)
        if not custom_authenticator:
            raise ValueError("Custom user context is enabled but not defined")

        return custom_auth_module, custom_authenticator
