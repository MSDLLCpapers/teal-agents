
from typing import Type

from ska_utils import Singleton, AppConfig, ModuleLoader
from .plugin_catalog import PluginCatalog
from configs import configs, TA_PLUGIN_CATALOG_MODULE, TA_PLUGIN_CATALOG_CLASS


class PluginCatalogFactory(Singleton):
    """
        Singleton factory for creating PluginCatalog
        instances based on environment variables.
    """

    def __init__(self):
        super().__init__()
        AppConfig.add_configs(configs)
        app_config = AppConfig()
        self.app_config = app_config
        self._catalog_instance: PluginCatalog | None = None

    def get_catalog(self) -> PluginCatalog:
        """
            Get the plugin catalog instance,
            creating it if it doesn't exist.
        """
        if self._catalog_instance is None:
            self._catalog_instance = self._create_catalog()
        return self._catalog_instance

    def _create_catalog(self) -> PluginCatalog:
        """
            Create a new plugin catalog instance
            based on environment variables.
        """
        module_name = self.app_config.get(
            TA_PLUGIN_CATALOG_MODULE.env_name
        )
        class_name = self.app_config.get(
            TA_PLUGIN_CATALOG_CLASS.env_name
        )

        if not module_name or not class_name:
            raise ValueError(
                "Both TA_PLUGIN_CATALOG_MODULE and TA_PLUGIN_CATALOG_CLASS "
                "environment variables must be set"
            )

        try:
            # Dynamically import the module
            module = ModuleLoader.load_module(module_name)

            # Get the class from the module
            catalog_class: Type[PluginCatalog] = getattr(
                module,
                class_name
            )

            # Verify it's a subclass of PluginCatalog
            if not issubclass(catalog_class, PluginCatalog):
                raise TypeError(
                    f"Class {class_name} in module {module_name} "
                    f"must inherit from PluginCatalog"
                )

            # Instantiate and return the catalog
            return catalog_class(self.app_config)

        except ImportError as e:
            raise ImportError(
                f"Failed to import module '{module_name}': {e}"
            ) from e
        except AttributeError as e:
            raise AttributeError(
                f"Class '{class_name}' not found in"
                f"module '{module_name}': {e}"
            ) from e
