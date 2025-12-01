"""Agent session management with per-task runners."""

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from semantic_kernel import Kernel
from config import Settings

from src.agent_runner import AgentResult, AgentRunner
from src.cli.models import ProjectConfig, SessionSettings, SessionState, TaskRecord
from src.cli.project_loader import ProjectLoader
from src.policies.hitl_config import HITLMode
from src.plugins.plugin_manager import PluginManager
from src.plugins.base_plugin import BasePlugin


class AgentSession:
    """Manages long-running agent session with per-task runners."""

    MAX_CONCURRENT_TASKS = 3

    def __init__(
        self,
        project_path: Path,
        config: ProjectConfig,
        logger: Optional[logging.Logger] = None,
    ):
        """Initialize agent session.

        Args:
            project_path: Path to project directory
            config: Project configuration
            logger: Optional logger instance
        """
        self.logger = logger or logging.getLogger(self.__class__.__name__)

        # Initialize session state
        initial_settings = SessionSettings(
            hitl_mode=HITLMode(config.default_hitl_mode),
            step_budget=config.default_step_budget,
            enable_feedback=config.enable_feedback,
        )

        self.state = SessionState(
            project_path=project_path,
            project_config=config,
            settings=initial_settings,
        )

        # Session-level plugin manager (shared across tasks)
        self.plugin_manager: Optional[PluginManager] = None
        self.loaded_plugins: List[BasePlugin] = []

        # Per-task runners
        self.task_runners: Dict[str, AgentRunner] = {}

        self._initialized = False

    async def initialize(self) -> None:
        """Initialize agent session.

        Loads plugins into session-level plugin manager.
        """
        if self._initialized:
            self.logger.warning("Session already initialized")
            return

        self.logger.info("Initializing agent session...")

        # Create session-level plugin manager
        kernel = Kernel()  # Temporary kernel just for plugin metadata
        self.plugin_manager = PluginManager(kernel, self.logger)

        # Load project plugins
        loader = ProjectLoader(self.state.project_path, logger=self.logger)
        plugins = loader.discover_plugins(self.state.project_config)

        for plugin in plugins:
            self.plugin_manager.register_plugin(plugin)
            self.loaded_plugins.append(plugin)
            self.state.plugins_loaded.append(plugin.plugin_name)

        self._initialized = True
        self.logger.info(f"Agent session initialized with {len(plugins)} plugin(s)")

    async def create_task_runner(
        self, task_id: str, task_config
    ) -> AgentRunner:
        """Create AgentRunner for a specific task.

        Args:
            task_id: Task identifier
            task_config: Task configuration

        Returns:
            Initialized AgentRunner

        Raises:
            RuntimeError: If max concurrent tasks reached
        """
        # Check concurrent limit
        if len(self.task_runners) >= self.MAX_CONCURRENT_TASKS:
            active_tasks = list(self.task_runners.keys())
            raise RuntimeError(
                f"Maximum {self.MAX_CONCURRENT_TASKS} concurrent tasks reached.\n"
                f"Active tasks: {', '.join(active_tasks)}\n"
                f"Use '/task cleanup <id>' to free resources."
            )

        # Create runner with task-specific settings
        runner = AgentRunner(
            settings=Settings(),
            hitl_mode=task_config.get_effective_hitl_mode(self.state.settings.hitl_mode),
            enable_feedback=self.state.settings.enable_feedback,
            log_level=self.state.project_config.log_level,
        )

        # Enter runner context
        await runner.__aenter__()

        # Register session plugins into task runner
        for plugin in self.loaded_plugins:
            runner.register_plugin(plugin)

        # Load context files for this task
        # (Could be task-specific in the future)
        loader = ProjectLoader(self.state.project_path, logger=self.logger)
        runbooks_path, examples_path = loader.find_context_files(
            self.state.project_config
        )

        if runbooks_path:
            try:
                runner.load_runbook(runbooks_path, runbook_id="wifi-rca")
            except KeyError:
                try:
                    runner.load_runbook(runbooks_path, runbook_id="plan-react-default")
                except KeyError:
                    try:
                        runner.load_runbook(runbooks_path, runbook_id="default")
                    except KeyError:
                        self.logger.warning(f"No compatible runbook found in {runbooks_path}")

        if examples_path:
            try:
                runner.load_examples(examples_path, example_id="plan-react")
            except KeyError:
                self.logger.warning(f"No plan-react examples found in {examples_path}")

        # Store runner
        self.task_runners[task_id] = runner
        self.logger.info(f"Created runner for {task_id}")

        return runner

    async def cleanup_task_runner(self, task_id: str) -> bool:
        """Cleanup specific task runner.

        Args:
            task_id: Task identifier

        Returns:
            True if cleaned up, False if not found
        """
        if task_id not in self.task_runners:
            return False

        runner = self.task_runners[task_id]
        await runner.__aexit__(None, None, None)
        del self.task_runners[task_id]

        self.logger.info(f"Cleaned up runner for {task_id}")
        return True

    async def cleanup(self) -> None:
        """Clean up all session resources."""
        # Cleanup all task runners
        for task_id in list(self.task_runners.keys()):
            await self.cleanup_task_runner(task_id)

        self._initialized = False

    async def run_task_with_runner(
        self, task_id: str, task: str, hints: Optional[list] = None
    ) -> AgentResult:
        """Execute a task using its runner.

        Args:
            task_id: Task identifier
            task: Task description
            hints: Optional hints for planning

        Returns:
            AgentResult with execution details
        """
        runner = self.task_runners.get(task_id)
        if not runner:
            raise RuntimeError(f"No runner found for {task_id}")

        start_time = time.perf_counter()

        # Execute task
        result = await runner.run(
            task=task,
            step_budget=self.state.settings.step_budget,
            hitl_mode=self.state.settings.hitl_mode,
            hints=hints,
        )

        duration = time.perf_counter() - start_time

        # Record task in history
        task_record = TaskRecord(
            task_id=len(self.state.task_history) + 1,
            task=task,
            success=result.success,
            duration=duration,
            steps_executed=result.steps_executed,
            timestamp=datetime.now().isoformat(),
        )
        self.state.add_task_record(task_record)

        return result

    def update_settings(self, setting: str, value: str) -> bool:
        """Update session setting.

        Args:
            setting: Setting name (hitl_mode, step_budget, etc.)
            value: New value as string

        Returns:
            True if successful, False otherwise
        """
        setting_lower = setting.lower()

        if setting_lower == "hitl_mode":
            return self.state.settings.update_hitl_mode(value)

        elif setting_lower == "step_budget":
            try:
                budget = int(value)
                if budget > 0:
                    self.state.settings.step_budget = budget
                    return True
            except ValueError:
                pass
            return False

        elif setting_lower == "feedback":
            value_lower = value.lower()
            if value_lower in ["true", "false", "yes", "no", "on", "off"]:
                enabled = value_lower in ["true", "yes", "on"]
                self.state.settings.enable_feedback = enabled
                return True
            return False

        return False

    def get_plugins_info(self) -> dict:
        """Get information about loaded plugins and their tools.

        Returns:
            Dictionary with plugin information
        """
        if not self.plugin_manager:
            return {}

        plugins_info = {}

        # Get tool manifest from session plugin manager
        manifest = self.plugin_manager.get_tool_manifest()

        for plugin_name, tools in manifest.items():
            plugins_info[plugin_name] = {
                "name": plugin_name,
                "tools": [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "risk_level": tool.risk_level.value,
                    }
                    for tool in tools.values()
                ],
            }

        return plugins_info

    def get_active_tasks(self) -> List[str]:
        """Get list of active task IDs with runners."""
        return list(self.task_runners.keys())

    @property
    def is_initialized(self) -> bool:
        """Check if session is initialized."""
        return self._initialized


__all__ = ["AgentSession"]
