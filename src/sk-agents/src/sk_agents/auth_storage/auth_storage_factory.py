from ska_utils import AppConfig, ModuleLoader

from sk_agents.configs import TA_AUTH_STORAGE_MANAGER_CLASS, TA_AUTH_STORAGE_MANAGER_MODULE

from sk_agents.auth_storage.in_memory_secure_auth_storage_manager import InMemorySecureAuthStorageManager
from sk_agents.auth_storage.singleton import Singleton

""""
The AuthStorageFactory is responsible for creating instances of authentication
storage managers, such as InMemorySecureAuthStorageManager.

It retrieves the module and class names from environment variables,
and  ensures the dynamically loaded class is a
subclass of InMemorySecureAuthStorageManager.

"""


class AuthStorageFactory(metaclass=Singleton):
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        module_name, class_name = self._get_auth_storage_config()

        try:
            self.module = ModuleLoader.load_module(module_name)
        except Exception as e:
            raise ImportError(f"Failed to load module '{module_name}': {e}") from e

        try:
            self.auth_storage_class = getattr(self.module, class_name)
        except AttributeError as e:
            raise ImportError(f"Class '{class_name}' not found in module '{module_name}'.") from e

        if not issubclass(self.auth_storage_class, InMemorySecureAuthStorageManager):
            raise TypeError(f"Class '{class_name}' is not a subclass of AuthStorageManager.")

    def get_auth_storage_manager(self) -> InMemorySecureAuthStorageManager:
        return self.auth_storage_class()

    def _get_auth_storage_config(self) -> tuple[str, str]:
        module_name = self.app_config.get(TA_AUTH_STORAGE_MANAGER_MODULE.env_name)
        class_name = self.app_config.get(TA_AUTH_STORAGE_MANAGER_CLASS.env_name)

        if not module_name:
            raise ValueError("Environment variable AUTH_STORAGE_MANAGER_MODULE is not set.")
        if not class_name:
            raise ValueError("Environment variable AUTH_STORAGE_MANAGER_CLASS is not set.")

        return module_name, class_name
