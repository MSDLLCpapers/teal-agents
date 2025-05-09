from pydantic import BaseModel
from ska_utils import AppConfig, ModuleLoader, strtobool

from auth.authenticator import Authenticator
from auth.user_id_only_authenticator import (
    UserIdOnlyAuthenticator,
    UserIdOnlyAuthRequest,
)
from configs import (
    TA_CUSTOM_AUTH_ENABLED,
    TA_CUSTOM_AUTH_MODULE,
    TA_CUSTOM_AUTH_REQUEST,
    TA_CUSTOM_AUTHENTICATOR,
)


class CustomAuthHelper:
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.custom_auth_enabled = strtobool(app_config.get(TA_CUSTOM_AUTH_ENABLED.env_name))
        if self.custom_auth_enabled:
            module_name, class_name, request_name = self._get_custom_auth_config()
            self.module = ModuleLoader.load_module(module_name)

    def get_request_type(self) -> type[BaseModel]:
        if self.custom_auth_enabled:
            return getattr(self.module, self.app_config.get(TA_CUSTOM_AUTH_REQUEST.env_name))
        else:
            return UserIdOnlyAuthRequest

    def get_authenticator(self) -> Authenticator:
        if not self.custom_auth_enabled:
            return UserIdOnlyAuthenticator()

        class_name = self.app_config.get(TA_CUSTOM_AUTHENTICATOR.env_name)
        return getattr(self.module, class_name)()

    def _get_custom_auth_config(self) -> tuple[str, str, str]:
        custom_auth_module = self.app_config.get(TA_CUSTOM_AUTH_MODULE.env_name)
        if not custom_auth_module:
            raise ValueError("Custom auth module is enabled but not defined")

        custom_authenticator = self.app_config.get(TA_CUSTOM_AUTHENTICATOR.env_name)
        if not custom_authenticator:
            raise ValueError("Custom authenticator is enabled but not defined")

        custom_auth_request = self.app_config.get(TA_CUSTOM_AUTH_REQUEST.env_name)
        if not custom_auth_request:
            raise ValueError("Custom auth request is enabled but not defined")

        return custom_auth_module, custom_authenticator, custom_auth_request
