# Factory implementation
from sk_agents.configs import (
    TA_PERSISTENCE_CLASS,
    TA_PERSISTENCE_MODULE
)
from ska_utils import AppConfig, ModuleLoader
from sk_agents.persistence.task_persistence_manager import (
    TaskPersistenceManager
)


class PersistenceFactory:
    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        module_name, class_name = self._get_custom_persistence_config()
        self.module = ModuleLoader.load_module(module_name)

    def get_persistence_manager(self) -> TaskPersistenceManager | None:
        class_name = self.app_config.get(TA_PERSISTENCE_CLASS.env_name)
        return getattr(self.module, class_name)()

    def _get_custom_persistence_config(self) -> tuple[str, str]:
        custom_persistence_module = self.app_config.get(
            TA_PERSISTENCE_MODULE.env_name
        )
        if not custom_persistence_module:
            raise ValueError(
                "Custom persistence module is enabled but not defined"
            )

        custom_persistence_manager_class = self.app_config.get(
            TA_PERSISTENCE_CLASS.env_name
        )
        if not custom_persistence_manager_class:
            raise ValueError(
                "Custom persistence is enabled but not defined"
            )

        return custom_persistence_module, custom_persistence_manager_class
