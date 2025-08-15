# src/sk_agents/plugincatalog/plugin_catalog.py
from abc import ABC, abstractmethod
from .models import Plugin, PluginTool


class PluginCatalog(ABC):
    @abstractmethod
    def get_plugin(self, plugin_id: str) -> Plugin | None:
        ...

    @abstractmethod
    def get_tool(self, tool_id: str) -> PluginTool | None:
        ...