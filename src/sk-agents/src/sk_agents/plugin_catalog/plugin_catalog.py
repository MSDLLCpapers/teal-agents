# src/sk_agents/plugincatalog/plugin_catalog.py
from abc import ABC, abstractmethod

from sk_agents.plugin_catalog.models import Plugin, PluginTool


class PluginCatalog(ABC):
    @abstractmethod
    def get_plugin(self, plugin_id: str) -> Plugin | None: ...

    @abstractmethod
    def get_tool(self, tool_id: str) -> PluginTool | None: ...

    # Dynamic registration methods for MCP and other runtime-discovered tools
    def register_dynamic_plugin(self, plugin: Plugin) -> None:
        """Register a plugin discovered at runtime (e.g., from MCP servers)."""
        # Default no-op implementation; subclasses may override
        _ = plugin

    def register_dynamic_tool(self, tool: PluginTool, plugin_id: str | None = None) -> None:
        """Register a tool discovered at runtime."""
        # Default no-op implementation; subclasses may override
        _ = tool, plugin_id

    def unregister_dynamic_plugin(self, plugin_id: str) -> bool:
        """Unregister a dynamically registered plugin."""
        return False  # Default implementation does nothing
