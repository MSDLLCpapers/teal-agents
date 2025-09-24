from ska_utils import AppConfig, ModuleLoader

from sk_agents.configs import TA_AUTH_STORAGE_MANAGER_CLASS, TA_AUTH_STORAGE_MANAGER_MODULE

from .in_memory_secure_auth_storage_manager import InMemorySecureAuthStorageManager
from .secure_auth_storage_manager import SecureAuthStorageManager
from .singleton import Singleton

""""
The AuthStorageFactory is responsible for creating instances of authentication
storage managers.

It retrieves the module and class names from environment variables for custom implementations,
and ensures the dynamically loaded class is a subclass of SecureAuthStorageManager.
Falls back to InMemorySecureAuthStorageManager when no custom module is provided.

"""


class AuthStorageFactory(metaclass=Singleton):
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config

        # Try to load custom module, fallback to default if not configured
        module_name, class_name = self._get_custom_auth_storage_config()
        if module_name and class_name:
            try:
                self.module = ModuleLoader.load_module(module_name)
            except Exception as e:
                raise ImportError(f"Failed to load module '{module_name}': {e}") from e

            self.class_name = class_name
            self._validate_custom_class()
        else:
            self.module = None
            self.class_name = None

    def get_auth_storage_manager(self) -> SecureAuthStorageManager:
        if self.module and self.class_name:
            # Use custom implementation
            custom_class = getattr(self.module, self.class_name)
            try:
                return custom_class(app_config=self.app_config)
            except TypeError:
                # Fallback if app_config not accepted
                return custom_class()
        else:
            # Use default implementation
            return InMemorySecureAuthStorageManager()

    def _get_custom_auth_storage_config(self) -> tuple[str | None, str | None]:
        """Get custom auth storage configuration, returning None values if not configured."""
        try:
            module_name = self.app_config.get(TA_AUTH_STORAGE_MANAGER_MODULE.env_name)
        except KeyError:
            return None, None

        try:
            class_name = self.app_config.get(TA_AUTH_STORAGE_MANAGER_CLASS.env_name)
        except KeyError:
            if module_name:
                raise ValueError("Custom Auth Storage Manager class name not provided") from None
            return None, None

        return module_name, class_name

    def _validate_custom_class(self):
        """Validate that the custom class is a proper SecureAuthStorageManager subclass."""
        if not hasattr(self.module, self.class_name):
            module_name = getattr(self.module, "__name__", "unknown module")
            raise ValueError(
                f"Custom Auth Storage Manager class: {self.class_name} "
                f"Not found in module: {module_name}"
            )

        custom_class = getattr(self.module, self.class_name)
        if not issubclass(custom_class, SecureAuthStorageManager):
            raise TypeError(
                f"Class '{self.class_name}' is not a subclass of SecureAuthStorageManager."
            )
