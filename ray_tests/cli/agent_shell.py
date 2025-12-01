"""Interactive shell for agent operations."""

import asyncio
import logging
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.history import InMemoryHistory

from src.cli.agent_session import AgentSession
from src.cli.commands import CommandRegistry, RunCommand
from src.cli.models import ProjectConfig
from src.cli.project_loader import ProjectLoader
from src.cli.tool_caller import ToolCaller


class CommandCompleter(Completer):
    """Auto-completer for CLI commands and tool calls."""

    def __init__(self, session: Optional[AgentSession] = None):
        """Initialize completer.
        
        Args:
            session: Agent session for tool completion
        """
        self.session = session

    def get_completions(self, document, complete_event):
        """Generate command completions.
        
        This is called on every keystroke when complete_while_typing=True,
        including backspace, so suggestions update in real-time.
        """
        text = document.text_before_cursor
        
        # Handle / commands
        if text.startswith('/'):
            # Get the command being typed (without the /)
            cmd_text = text[1:].lower()
            
            # Get all available commands
            commands = CommandRegistry.get_all_commands()
            
            # Filter commands that match (or all if cmd_text is empty)
            for command in commands:
                cmd_name = command.name
                if not cmd_text or cmd_name.startswith(cmd_text):
                    yield Completion(
                        cmd_name,
                        start_position=-len(cmd_text),
                        display=f"/{cmd_name}",
                        display_meta=command.description,
                        selected_style="class:completion-menu.completion.current",
                        style="class:completion-menu.completion",
                    )
        
        # Handle @ tool calls
        elif text.startswith('@') and self.session:
            # Get the tool being typed (without the @)
            tool_text = text[1:]
            
            # Get all available tools
            plugins_info = self.session.get_plugins_info()
            
            for plugin_name, info in plugins_info.items():
                for tool in info["tools"]:
                    tool_name = tool["name"]
                    full_name = f"{plugin_name}.{tool_name}"
                    
                    # Match if tool_text is empty or full_name starts with it
                    if not tool_text or full_name.lower().startswith(tool_text.lower()):
                        risk = tool["risk_level"]
                        desc = tool["description"][:60] + "..." if len(tool["description"]) > 60 else tool["description"]
                        
                        yield Completion(
                            full_name,
                            start_position=-len(tool_text),
                            display=f"@{full_name}",
                            display_meta=f"[{risk}] {desc}",
                            selected_style="class:completion-menu.completion.current",
                            style="class:completion-menu.completion",
                        )


class AgentShell:
    """Interactive shell for running agents."""

    def __init__(self, project_path: Path, logger: Optional[logging.Logger] = None):
        """Initialize agent shell.

        Args:
            project_path: Path to project directory
            logger: Optional logger instance
        """
        self.project_path = project_path.resolve()
        self.logger = logger or logging.getLogger(self.__class__.__name__)
        self.session: Optional[AgentSession] = None
        self.running = False

    async def start(self) -> None:
        """Start interactive shell session."""
        try:
            # Print banner
            self._print_banner()

            # Load project
            print(f"\nLoading project from: {self.project_path}")

            loader = ProjectLoader(self.project_path, logger=self.logger)
            config = loader.load_config()

            # Initialize session
            self.session = AgentSession(
                project_path=self.project_path, config=config, logger=self.logger
            )

            # Print initialization status
            print("\nInitializing agent runtime...")

            await self.session.initialize()

            # Print loaded components
            self._print_initialization_summary()

            # Start command loop
            await self._command_loop()

        except KeyboardInterrupt:
            print("\n\nInterrupted by user")
        except Exception as e:
            self.logger.error(f"Shell error: {e}", exc_info=True)
            print(f"\n✗ Error: {e}")
        finally:
            await self._cleanup()

    def _print_banner(self) -> None:
        """Print welcome banner."""
        print("=" * 70)
        print("🤖 Agent Platform Interactive CLI")
        print("=" * 70)

    def _print_initialization_summary(self) -> None:
        """Print summary of loaded components."""
        if not self.session:
            return

        config = self.session.state.project_config
        plugins = self.session.state.plugins_loaded

        print(f"\n✓ Project: {config.name}")
        if config.description:
            print(f"  {config.description}")

        print(f"✓ Loaded {len(plugins)} plugin(s):")
        for plugin in plugins:
            print(f"  - {plugin}")

        # Show context files loaded
        if config.runbooks_path:
            print(f"✓ Runbooks: {config.runbooks_path}")
        if config.examples_path:
            print(f"✓ Examples: {config.examples_path}")

        print(f"✓ Runtime initialized")

        # Show current settings
        print("\nCurrent Settings:")
        settings_dict = self.session.state.settings.to_dict()
        for key, value in settings_dict.items():
            print(f"  {key}: {value}")

        print("\nType /help for available commands")
        print("=" * 70)

    async def _command_loop(self) -> None:
        """Main command loop with auto-completion."""
        self.running = True
        
        # Create prompt session with history and auto-completion
        from prompt_toolkit.completion import ThreadedCompleter
        
        # Pass session to completer for @ tool completion
        prompt_session = PromptSession(
            history=InMemoryHistory(),
            completer=ThreadedCompleter(CommandCompleter(session=self.session)),
            complete_while_typing=True,
            complete_in_thread=True,
            enable_history_search=False,
            # These settings ensure completions show even after backspace
            mouse_support=False,  # Disable mouse to avoid conflicts
            enable_suspend=False,  # Keep completions active
        )

        while self.running:
            try:
                # Get user input with auto-completion
                user_input = await self._get_input_with_completion(
                    prompt_session, "\nagent> "
                )

                if not user_input:
                    continue

                # Check if it's a tool call with @
                if user_input.startswith('@'):
                    tool_caller = ToolCaller(self.session)
                    await tool_caller.execute(user_input)
                    continue

                # Parse input for / commands
                command, args = CommandRegistry.parse_input(user_input)

                if command:
                    # Execute command
                    continue_running = await command.execute(
                        self.session, args, print
                    )
                    self.running = continue_running
                else:
                    # Treat as task if not a command
                    await self._execute_task(user_input)

            except KeyboardInterrupt:
                print("\n(Use /exit to quit)")
            except Exception as e:
                self.logger.error(f"Command error: {e}", exc_info=True)
                print(f"\n✗ Error: {e}")

    async def _get_input_with_completion(
        self, prompt_session: PromptSession, prompt: str
    ) -> str:
        """Get user input with auto-completion support.

        Args:
            prompt_session: PromptSession instance with completer
            prompt: Input prompt to display

        Returns:
            User input string
        """
        # Run prompt_async in thread pool to keep event loop responsive
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, lambda: prompt_session.prompt(prompt)
        )

    async def _execute_task(self, task: str) -> None:
        """Execute a task directly (without command prefix).

        Args:
            task: Task description
        """
        # Inform user to use /task new instead
        print("\n[Info] Plain text task execution is deprecated.")
        print("Please use: /task new")
        print()

    async def _cleanup(self) -> None:
        """Clean up session resources."""
        if self.session:
            print("\nCleaning up...")
            await self.session.cleanup()
            print("Done")


__all__ = ["AgentShell"]
