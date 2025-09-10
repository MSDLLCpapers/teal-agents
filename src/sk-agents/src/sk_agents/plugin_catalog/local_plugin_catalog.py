import json
from pathlib import Path

from ska_utils import AppConfig

from sk_agents.configs import TA_PLUGIN_CATALOG_FILE
from sk_agents.exceptions import PluginCatalogDefinitionException, PluginFileReadException
from sk_agents.plugin_catalog.models import Plugin, PluginCatalogDefinition, PluginTool
from sk_agents.plugin_catalog.plugin_catalog import PluginCatalog


class FileBasedPluginCatalog(PluginCatalog):
    """File-based implementation that loads plugins from JSON files."""

    def __init__(self, app_config: AppConfig):
        self.app_config = app_config
        self.catalog_path = Path(self.app_config.get(TA_PLUGIN_CATALOG_FILE.env_name))
        self._plugins: dict[str, Plugin] = {}
        self._tools: dict[str, PluginTool] = {}
        self._load_plugins()

    def get_plugin(self, plugin_id: str) -> Plugin | None:
        """Get a plugin by its ID."""
        return self._plugins.get(plugin_id)

    def get_tool(self, tool_id: str) -> PluginTool | None:
        """Get a tool by its ID."""
        return self._tools.get(tool_id)

    def _load_plugins(self) -> None:
        """Load plugins from a single JSON file."""
        if not self.catalog_path.exists():
            return

        try:
            with open(self.catalog_path) as local_plugin_json:
                catalog_data = json.load(local_plugin_json)

            # Validate and convert to PluginCatalogDefinition
            try:
                catalog_definition = PluginCatalogDefinition.model_validate(catalog_data)
            except Exception as validation_error:
                raise PluginCatalogDefinitionException(
                    message="Plugin catalog definition validation failed"
                ) from validation_error
            # Process the validated plugins
            for plugin_data in catalog_definition.plugins:
                plugin = plugin_data
                self._plugins[plugin.plugin_id] = plugin

                # Index tools for quick lookup
                for tool in plugin.tools:
                    self._tools[tool.tool_id] = tool

        except PluginCatalogDefinitionException:
            # Re-raise our custom exception
            raise
        except Exception as e:
            raise PluginFileReadException(
                message="""
                Catalog encountered an error
                when attempting to read file
                """
            ) from e
