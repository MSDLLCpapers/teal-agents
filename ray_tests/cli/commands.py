"""Command system for interactive CLI."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional

if TYPE_CHECKING:
    from src.cli.agent_session import AgentSession


class Command(ABC):
    """Base class for CLI commands."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Command name (e.g., 'help')."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Short description of command."""
        pass

    @property
    def usage(self) -> str:
        """Usage string for command."""
        return f"/{self.name}"

    @abstractmethod
    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        """Execute the command.

        Args:
            session: Current agent session
            args: Command arguments (excluding command name)
            output: Function to call for output (output(text))

        Returns:
            True to continue, False to exit shell
        """
        pass


class HelpCommand(Command):
    """Show available commands."""

    @property
    def name(self) -> str:
        return "help"

    @property
    def description(self) -> str:
        return "Show available commands"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        from src.cli.commands import CommandRegistry

        output("\nAvailable Commands:")
        output("=" * 60)

        for cmd in CommandRegistry.get_all_commands():
            output(f"  {cmd.usage:20s} - {cmd.description}")

        output("\nYou can also type any text to start a task without /run prefix")
        output("=" * 60)
        return True


class StatusCommand(Command):
    """Show session status."""

    @property
    def name(self) -> str:
        return "status"

    @property
    def description(self) -> str:
        return "Show agent status and loaded plugins"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        output("\nSession Status:")
        output("=" * 60)
        output(f"Project: {session.state.project_config.name}")
        output(f"Path: {session.state.project_path}")
        output(f"Plugins Loaded: {len(session.state.plugins_loaded)}")

        if session.state.plugins_loaded:
            for plugin in session.state.plugins_loaded:
                output(f"  - {plugin}")

        output(f"Tasks Completed: {session.state.get_task_count()}")
        output("=" * 60)
        return True


class SettingsCommand(Command):
    """View/change settings."""

    @property
    def name(self) -> str:
        return "settings"

    @property
    def description(self) -> str:
        return "View/change session settings"

    @property
    def usage(self) -> str:
        return "/settings [setting=value]"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        if not args:
            # Show current settings
            output("\nCurrent Settings:")
            output("=" * 60)
            settings_dict = session.state.settings.to_dict()
            for key, value in settings_dict.items():
                output(f"  {key:20s}: {value}")
            output("\nUsage: /settings <setting>=<value>")
            output("Available settings: hitl_mode, step_budget, feedback")
            output("=" * 60)
            return True

        # Parse setting=value
        setting_str = " ".join(args)
        if "=" not in setting_str:
            output("Invalid format. Use: /settings setting=value")
            return True

        setting, value = setting_str.split("=", 1)
        setting = setting.strip()
        value = value.strip()

        success = session.update_settings(setting, value)

        if success:
            output(f"✓ Setting '{setting}' updated to '{value}'")
        else:
            output(f"✗ Failed to update setting '{setting}'")
            output("Valid settings: hitl_mode, step_budget, feedback")
            output(
                "Valid HITL modes: autonomous, strategic_review, guided_automation, manual"
            )

        return True


class PluginsCommand(Command):
    """List plugins and tools."""

    @property
    def name(self) -> str:
        return "plugins"

    @property
    def description(self) -> str:
        return "List available plugins and tools"

    @property
    def usage(self) -> str:
        return "/plugins [explore]"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        # Check if explore mode requested
        if args and args[0].lower() == "explore":
            from src.cli.plugin_explorer import PluginExplorer
            
            explorer = PluginExplorer(session)
            await explorer.start()
            return True

        # Default: Simple list view
        plugins_info = session.get_plugins_info()

        if not plugins_info:
            output("No plugins loaded")
            return True

        output("\nAvailable Plugins:")
        output("=" * 60)

        for plugin_name, info in plugins_info.items():
            output(f"\n{plugin_name}:")
            for tool in info["tools"]:
                risk = tool["risk_level"]
                output(f"  - {tool['name']:25s} [{risk:8s}]")
                if args and "verbose" in args:
                    output(f"    {tool['description']}")

        output("\nTip: Use '/plugins explore' for interactive mode")
        output("=" * 60)
        return True


class TaskCommand(Command):
    """Manage and execute tasks."""

    @property
    def name(self) -> str:
        return "task"

    @property
    def description(self) -> str:
        return "Create and manage tasks"

    @property
    def usage(self) -> str:
        return "/task [new|list]"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        if not args:
            output("Usage: /task [new|list|status|cleanup|cleanup-completed|cleanup-all]")
            output("  /task new                - Create and run a new task (interactive)")
            output("  /task list               - List active and completed tasks")
            output("  /task status             - Show resource usage dashboard")
            output("  /task cleanup <id>        - Cleanup specific task runner")
            output("  /task cleanup-completed  - Cleanup all completed task runners")
            output("  /task cleanup-all        - Cleanup ALL task runners (with confirmation)")
            return True

        subcommand = args[0].lower()

        if subcommand == "new":
            from src.cli.task_interface import TaskInterface

            task_interface = TaskInterface(session)
            await task_interface.start()
            return True

        elif subcommand == "list":
            from src.cli.task_interface import TaskManager

            task_manager = TaskManager(session)
            await task_manager.list_tasks()
            return True

        elif subcommand == "status":
            from src.cli.task_interface import TaskManager

            task_manager = TaskManager(session)
            await task_manager.show_status_dashboard()
            return True

        elif subcommand == "cleanup":
            if len(args) < 2:
                output("Usage: /task cleanup <task_id>")
                output("Example: /task cleanup task_01")
                return True

            task_id = args[1]
            success = await session.cleanup_task_runner(task_id)

            if success:
                output(f"✓ Cleaned up runner for {task_id}")
            else:
                output(f"✗ No active runner found for {task_id}")

            return True

        elif subcommand == "cleanup-completed":
            from src.cli.task_interface import TaskManager

            task_manager = TaskManager(session)
            await task_manager.cleanup_completed_tasks()
            return True

        elif subcommand == "cleanup-all":
            from src.cli.task_interface import TaskManager

            task_manager = TaskManager(session)
            await task_manager.cleanup_all_tasks()
            return True

        else:
            output(f"Unknown subcommand: {subcommand}")
            output("Use: /task new, /task list, /task status, /task cleanup, etc.")
            return True


class RunCommand(Command):
    """Execute a task (deprecated - use /task new)."""

    @property
    def name(self) -> str:
        return "run"

    @property
    def description(self) -> str:
        return "DEPRECATED - Use /task new instead"

    @property
    def usage(self) -> str:
        return "/run (deprecated)"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        output("\n[yellow]⚠️  /run is deprecated[/yellow]")
        output("The new architecture uses per-task runners for better isolation.")
        output("\nPlease use: /task new")
        output("This provides:")
        output("  - Task-specific configuration")
        output("  - Better resource management")
        output("  - Concurrent task support")
        output("  - Live execution progress")
        return True


class HistoryCommand(Command):
    """Show task history."""

    @property
    def name(self) -> str:
        return "history"

    @property
    def description(self) -> str:
        return "Show task history"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        if not session.state.task_history:
            output("No tasks in history")
            return True

        output("\nTask History:")
        output("=" * 60)

        for record in session.state.task_history[-10:]:  # Show last 10
            status = "✓" if record.success else "✗"
            output(
                f"{status} [{record.task_id}] {record.task[:50]} "
                f"({record.duration:.1f}s, {record.steps_executed} steps)"
            )

        output("=" * 60)
        return True


class ClearCommand(Command):
    """Clear screen."""

    @property
    def name(self) -> str:
        return "clear"

    @property
    def description(self) -> str:
        return "Clear the screen"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        import os

        os.system("clear" if os.name != "nt" else "cls")
        return True


class ExitCommand(Command):
    """Exit the shell."""

    @property
    def name(self) -> str:
        return "exit"

    @property
    def description(self) -> str:
        return "Exit agent session"

    async def execute(
        self, session: "AgentSession", args: List[str], output: callable
    ) -> bool:
        task_count = session.state.get_task_count()
        active_runners = len(session.task_runners)
        
        output(f"\n👋 Goodbye! {task_count} task(s) completed in this session.")
        
        if active_runners > 0:
            output(f"Note: {active_runners} task runner(s) will be cleaned up.")

        return False  # Signal to exit


class CommandRegistry:
    """Registry of available commands."""

    _commands: Dict[str, Command] = {
        "help": HelpCommand(),
        "status": StatusCommand(),
        "settings": SettingsCommand(),
        "plugins": PluginsCommand(),
        "task": TaskCommand(),
        "run": RunCommand(),
        "history": HistoryCommand(),
        "clear": ClearCommand(),
        "exit": ExitCommand(),
    }

    @classmethod
    def get_command(cls, name: str) -> Optional[Command]:
        """Get command by name."""
        return cls._commands.get(name.lower())

    @classmethod
    def get_all_commands(cls) -> List[Command]:
        """Get all registered commands."""
        return list(cls._commands.values())

    @classmethod
    def parse_input(cls, user_input: str) -> tuple[Optional[Command], List[str]]:
        """Parse user input into command and arguments.

        Returns:
            Tuple of (command, args) or (None, []) if not a command
        """
        user_input = user_input.strip()

        if not user_input.startswith("/"):
            # Not a command, treat as task
            return None, []

        # Remove leading /
        parts = user_input[1:].split()

        if not parts:
            return None, []

        cmd_name = parts[0]
        args = parts[1:]

        command = cls.get_command(cmd_name)
        return command, args


__all__ = ["Command", "CommandRegistry"]
