from ska_utils import AppConfig, ModuleLoader

from sk_agents.configs import TA_AUTHORIZER_CLASS, TA_AUTHORIZER_MODULE

from .request_authorizer import RequestAuthorizer
from .singleton import Singleton as Singleton


class AuthorizerFactory(metaclass=Singleton):
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        module_name, class_name = self._get_authorizer_config()

        try:
            self.module = ModuleLoader.load_module(module_name)
        except Exception as e:
            raise ImportError(f"Failed to load module '{module_name}': {e}") from e

        try:
            self.authorizer_class = getattr(self.module, class_name)
        except AttributeError as e:
            raise ImportError(f"Class '{class_name}' not found in module '{module_name}'.") from e

        if not issubclass(self.authorizer_class, RequestAuthorizer):
            raise TypeError(f"Class '{class_name}' is not a subclass of RequestAuthorizer.")

    def get_authorizer(self) -> RequestAuthorizer:
        return self.authorizer_class()

    def _get_authorizer_config(self) -> tuple[str, str]:
        module_name = self.app_config.get(TA_AUTHORIZER_MODULE.env_name)
        class_name = self.app_config.get(TA_AUTHORIZER_CLASS.env_name)

        if not module_name:
            raise ValueError("Environment variable TA_AUTHORIZER_MODULE is not set.")
        if not class_name:
            raise ValueError("Environment variable TA_AUTHORIZER_CLASS is not set.")

        return module_name, class_name
