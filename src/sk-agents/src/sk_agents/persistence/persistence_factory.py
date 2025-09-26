from ska_utils import AppConfig, ModuleLoader

from sk_agents.configs import TA_PERSISTENCE_CLASS, TA_PERSISTENCE_MODULE

from .in_memory_persistence_manager import InMemoryPersistenceManager
from .singleton import Singleton
from .task_persistence_manager import TaskPersistenceManager

"""
The PersistenceFactory is responsible for creating instances of task
persistence managers.

It retrieves the module and class names from environment variables for custom implementations,
and ensures the dynamically loaded class is a subclass of TaskPersistenceManager.
Falls back to InMemoryPersistenceManager when no custom module is provided.

"""


class PersistenceFactory(metaclass=Singleton):
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config

        # Try to load custom module, fallback to default if not configured
        module_name, class_name = self._get_custom_persistence_config()
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

    def get_persistence_manager(self) -> TaskPersistenceManager:
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
            return InMemoryPersistenceManager()

    def _get_custom_persistence_config(self) -> tuple[str | None, str | None]:
        """Get custom persistence configuration, returning None values if using defaults."""
        module_name = self.app_config.get(TA_PERSISTENCE_MODULE.env_name)
        class_name = self.app_config.get(TA_PERSISTENCE_CLASS.env_name)

        # Check if we're using the default values (which means no custom config)
        if (
            module_name == TA_PERSISTENCE_MODULE.default_value
            and class_name == TA_PERSISTENCE_CLASS.default_value
        ):
            return None, None

        return module_name, class_name

    def _validate_custom_class(self):
        """Validate that the custom class is a proper TaskPersistenceManager subclass."""
        if not hasattr(self.module, self.class_name):
            module_name = getattr(self.module, "__name__", "unknown module")
            raise ValueError(
                f"Custom Task Persistence Manager class: {self.class_name} "
                f"Not found in module: {module_name}"
            )

        custom_class = getattr(self.module, self.class_name)
        if not issubclass(custom_class, TaskPersistenceManager):
            raise TypeError(
                f"Class '{self.class_name}' is not a subclass of TaskPersistenceManager."
            )
