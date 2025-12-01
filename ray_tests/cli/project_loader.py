"""Project discovery and loading utilities."""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.cli.models import ProjectConfig
from src.plugins.base_plugin import BasePlugin


class ProjectLoader:
    """Discovers and loads project configuration, plugins, and context."""

    def __init__(self, project_path: Path, logger: Optional[logging.Logger] = None):
        """Initialize project loader.

        Args:
            project_path: Path to project directory
            logger: Optional logger instance
        """
        self.project_path = project_path.resolve()
        self.logger = logger or logging.getLogger(self.__class__.__name__)

        if not self.project_path.exists():
            raise FileNotFoundError(f"Project path does not exist: {project_path}")

        if not self.project_path.is_dir():
            raise NotADirectoryError(f"Project path is not a directory: {project_path}")

    def load_config(self) -> ProjectConfig:
        """Load project configuration.

        Looks for agent_config.yaml in project directory.
        If not found, returns default configuration.

        Returns:
            ProjectConfig instance
        """
        config_path = self.project_path / "agent_config.yaml"

        if config_path.exists():
            self.logger.info(f"Loading configuration from {config_path}")
            return ProjectConfig.from_yaml(config_path)
        else:
            self.logger.info("No agent_config.yaml found, using defaults")
            return ProjectConfig.from_defaults(self.project_path)

    def discover_plugins(self, config: ProjectConfig) -> List[BasePlugin]:
        """Discover and load plugins from project.

        Args:
            config: Project configuration

        Returns:
            List of loaded plugin instances
        """
        if not config.plugins_auto_discover:
            self.logger.info("Plugin auto-discovery disabled")
            return []

        plugins = []

        for plugin_path_str in config.plugins_paths:
            plugin_dir = self.project_path / plugin_path_str

            if not plugin_dir.exists():
                self.logger.debug(f"Plugin directory not found: {plugin_dir}")
                continue

            self.logger.info(f"Discovering plugins in: {plugin_dir}")

            # Add plugin directory to Python path
            if str(plugin_dir.parent) not in sys.path:
                sys.path.insert(0, str(plugin_dir.parent))

            # Find all Python files in plugin directory
            for py_file in plugin_dir.glob("*.py"):
                if py_file.name.startswith("_"):
                    continue  # Skip __init__.py and private modules

                try:
                    plugin = self._load_plugin_from_file(py_file)
                    if plugin:
                        plugins.append(plugin)
                        self.logger.info(f"Loaded plugin: {plugin.plugin_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to load plugin from {py_file}: {e}")

        return plugins

    def _load_plugin_from_file(self, file_path: Path) -> Optional[BasePlugin]:
        """Load a plugin from a Python file.

        Args:
            file_path: Path to Python file

        Returns:
            Plugin instance if found, None otherwise
        """
        module_name = file_path.stem

        # Load module
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        # Find BasePlugin subclasses
        for attr_name in dir(module):
            attr = getattr(module, attr_name)

            # Check if it's a class that inherits from BasePlugin
            if (
                isinstance(attr, type)
                and issubclass(attr, BasePlugin)
                and attr is not BasePlugin
            ):
                # Instantiate plugin
                return attr(logger=self.logger.getChild(attr_name))

        return None

    def find_context_files(
        self, config: ProjectConfig
    ) -> Tuple[Optional[Path], Optional[Path]]:
        """Find runbook and examples files.

        Args:
            config: Project configuration

        Returns:
            Tuple of (runbook_path, examples_path), None if not found
        """
        runbooks_path = None
        examples_path = None

        if config.runbooks_path:
            path = self.project_path / config.runbooks_path
            if path.exists():
                runbooks_path = path
                self.logger.info(f"Found runbooks: {path}")
            else:
                self.logger.debug(f"Runbooks file not found: {path}")

        if config.examples_path:
            path = self.project_path / config.examples_path
            if path.exists():
                examples_path = path
                self.logger.info(f"Found examples: {path}")
            else:
                self.logger.debug(f"Examples file not found: {path}")

        return runbooks_path, examples_path

    def get_data_paths(self, config: ProjectConfig) -> Dict[str, Path]:
        """Get resolved data paths from configuration.

        Args:
            config: Project configuration

        Returns:
            Dictionary of data name to resolved path
        """
        data_paths = {}

        for name, path_str in config.data_paths.items():
            path = self.project_path / path_str
            if path.exists():
                data_paths[name] = path
                self.logger.debug(f"Found data file '{name}': {path}")
            else:
                self.logger.warning(f"Data file '{name}' not found: {path}")

        return data_paths


__all__ = ["ProjectLoader"]
