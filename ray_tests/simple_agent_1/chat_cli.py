#!/usr/bin/env python3
"""
Interactive CLI for FileAssistant agent.

Usage:
    python chat_cli.py

Commands:
    /exit or /quit - Exit the CLI
    /clear - Clear the screen
    /new - Start a new session
    /help - Show help message
"""

import asyncio
import logging
import sys
from pathlib import Path

from prompt_toolkit import PromptSession
from prompt_toolkit.history import InMemoryHistory
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel

from agent_client import DirectAgentClient


# Configure logging
logging.basicConfig(
    level=logging.WARNING,  # Only show warnings and errors
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class ChatCLI:
    """Interactive chat CLI for FileAssistant."""

    def __init__(self, project_dir: Path):
        """
        Initialize the chat CLI.

        Args:
            project_dir: Path to the project directory
        """
        self.project_dir = project_dir
        self.client = DirectAgentClient(project_dir)
        self.console = Console()
        self.running = False
        self.prompt_session = PromptSession(history=InMemoryHistory())

    def print_banner(self):
        """Print welcome banner."""
        self.console.print()
        self.console.print("=" * 70, style="bold cyan")
        self.console.print(
            "  🤖 FileAssistant Interactive CLI", 
            style="bold cyan",
            justify="center"
        )
        self.console.print("=" * 70, style="bold cyan")
        self.console.print()

    def print_help(self):
        """Print help message."""
        help_text = """
## Available Commands

- `/exit` or `/quit` - Exit the CLI
- `/clear` - Clear the screen
- `/new` - Start a new session (clear chat history)
- `/plugins` - Show available tools
- `/help` - Show this help message

## Direct Tool Calling

Use `@` to call tools directly (bypass the LLM):

```
@PluginName.function_name
@PluginName.function_name arg1="value1" arg2="value2"
```

Examples:
```
@FilePlugin.list_files
@FilePlugin.read_file filename="sample.txt"
@FilePlugin.search_files pattern="*.json"
```

## Chat Usage

Just type your message to chat with the agent.
The agent has access to files in the `data/` directory.

Examples:
```
> List all files
> Read sample.txt
> Find all JSON files
```
"""
        self.console.print(Panel(Markdown(help_text), title="Help", border_style="blue"))

    async def initialize(self):
        """Initialize the client."""
        self.console.print("🔧 Initializing agent...", style="yellow")
        try:
            await self.client.initialize()
            self.console.print("✅ Agent ready!", style="green")
            self.console.print()
            self.console.print(
                "Type your message or /help for available commands",
                style="dim"
            )
            self.console.print()
        except Exception as e:
            self.console.print(f"❌ Failed to initialize: {e}", style="bold red")
            raise

    async def handle_command(self, command: str) -> bool:
        """
        Handle CLI commands.

        Args:
            command: Command string (starting with /)

        Returns:
            True to continue, False to exit
        """
        cmd = command.lower().strip()

        if cmd in ["/exit", "/quit"]:
            self.console.print("\n👋 Goodbye!", style="cyan")
            return False

        elif cmd == "/clear":
            self.console.clear()
            self.print_banner()
            return True

        elif cmd == "/new":
            session_id = self.client.new_session()
            self.console.print(f"\n✨ Started new session: {session_id[:8]}...", style="green")
            return True

        elif cmd == "/plugins":
            await self.show_plugins()
            return True

        elif cmd == "/help":
            self.print_help()
            return True

        else:
            self.console.print(f"❓ Unknown command: {command}", style="yellow")
            self.console.print("Type /help for available commands", style="dim")
            return True

    async def show_plugins(self):
        """Show available plugins and their tools."""
        self.console.print("\n🔧 Loading plugin information...", style="yellow")

        try:
            # Pass current session_id to include MCP plugins discovered in this session
            tools_by_plugin = await self.client.get_available_tools(
                session_id=self.client.session_id
            )
            
            if not tools_by_plugin:
                self.console.print("\n⚠️  No plugins found!", style="yellow")
                return
            
            self.console.print()
            self.console.print("=" * 70, style="cyan")
            self.console.print("  Available Plugins and Tools", style="bold cyan")
            self.console.print("=" * 70, style="cyan")
            
            for plugin_name, tools in tools_by_plugin.items():
                self.console.print(f"\n[bold green]{plugin_name}[/bold green]:")
                
                for tool in tools:
                    self.console.print(f"  • [cyan]{tool['name']}[/cyan]")
                    self.console.print(f"    {tool['description']}", style="dim")
                    
                    if tool['parameters']:
                        params_str = ", ".join([
                            f"{p['name']}: {p['type']}" + (" (required)" if p['required'] else "")
                            for p in tool['parameters']
                        ])
                        self.console.print(f"    Parameters: {params_str}", style="dim italic")
                    
                    # Show usage example
                    params_example = " ".join([
                        f'{p["name"]}="{p["type"]}"' 
                        for p in tool['parameters']
                    ])
                    if params_example:
                        self.console.print(
                            f"    Usage: @{plugin_name}.{tool['name']} {params_example}",
                            style="dim blue"
                        )
                    else:
                        self.console.print(
                            f"    Usage: @{plugin_name}.{tool['name']}",
                            style="dim blue"
                        )
            
            self.console.print("\n" + "=" * 70, style="cyan")
            self.console.print()
            
        except Exception as e:
            self.console.print(f"\n❌ Error loading plugins: {e}", style="bold red")
            logger.error(f"Error showing plugins: {e}", exc_info=True)

    async def handle_tool_call(self, tool_call: str):
        """
        Handle direct tool calling with @ syntax.

        Args:
            tool_call: Tool call string (e.g., "@FilePlugin.list_files" or "@FilePlugin.read_file filename='sample.txt'")
        """
        try:
            # Remove @ prefix
            tool_str = tool_call[1:].strip()
            
            # Parse plugin.function and arguments
            # Format: PluginName.function_name arg1="val1" arg2="val2"
            parts = tool_str.split(None, 1)
            tool_path = parts[0]
            args_str = parts[1] if len(parts) > 1 else ""
            
            # Split plugin and function
            if "." not in tool_path:
                self.console.print("❌ Invalid format. Use: @PluginName.function_name", style="red")
                return
            
            plugin_name, function_name = tool_path.rsplit(".", 1)
            
            # Parse arguments (simple key="value" parser)
            kwargs = {}
            if args_str:
                import re
                # Match key="value" or key='value' patterns
                arg_pattern = r'(\w+)=(["\'])([^\2]*?)\2'
                for match in re.finditer(arg_pattern, args_str):
                    key, _, value = match.groups()
                    kwargs[key] = value
            
            self.console.print(f"\n🔧 Calling {plugin_name}.{function_name}...", style="yellow")

            # Call the tool (pass session_id to include MCP plugins)
            result = await self.client.call_tool(
                plugin_name,
                function_name,
                session_id=self.client.session_id,
                **kwargs
            )
            
            # Display result
            self.console.print()
            self.console.print(
                Panel(
                    Markdown(f"```\n{result}\n```"),
                    title=f"📋 Result: {plugin_name}.{function_name}",
                    border_style="green"
                )
            )
            self.console.print()
            
        except Exception as e:
            self.console.print(f"\n❌ Error calling tool: {e}", style="bold red")
            logger.error(f"Error in tool call: {e}", exc_info=True)

    async def stream_response(self, message: str):
        """
        Send message and stream the response.

        Args:
            message: User message
        """
        self.console.print()
        self.console.print("[dim]Press Ctrl+C or ESC to cancel[/dim]")
        self.console.print()
        
        # Accumulate response for display
        response_text = ""
        cancelled = False
        
        try:
            # Use Rich Live for streaming display
            with Live("", console=self.console, refresh_per_second=10) as live:
                async for chunk in self.client.chat(message):
                    response_text += chunk
                    # Update the live display with accumulated response
                    live.update(
                        Panel(
                            Markdown(response_text if response_text else "_Waiting for response..._"),
                            title="🤖 FileAssistant",
                            border_style="green",
                        )
                    )
            
            # Print final newline
            self.console.print()

        except asyncio.CancelledError:
            cancelled = True
            self.console.print("\n⚠️  [yellow]Response cancelled by user[/yellow]")
            if response_text:
                self.console.print("\nPartial response received:")
                self.console.print(Panel(Markdown(response_text), border_style="yellow"))
            self.console.print()
        except KeyboardInterrupt:
            cancelled = True
            self.console.print("\n⚠️  [yellow]Response cancelled by user[/yellow]")
            if response_text:
                self.console.print("\nPartial response received:")
                self.console.print(Panel(Markdown(response_text), border_style="yellow"))
            self.console.print()
        except Exception as e:
            self.console.print(f"\n❌ Error: {e}", style="bold red")
            logger.error(f"Error streaming response: {e}", exc_info=True)

    async def run(self):
        """Run the interactive CLI loop."""
        self.print_banner()
        await self.initialize()
        
        self.running = True

        while self.running:
            try:
                # Get user input
                user_input = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: self.prompt_session.prompt("\n💬 You: ", default="")
                )

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    self.running = await self.handle_command(user_input)
                    continue

                # Handle direct tool calls
                if user_input.startswith("@"):
                    await self.handle_tool_call(user_input)
                    continue

                # Send message and stream response (with cancellation support)
                # Create a task so we can cancel it with Ctrl+C
                stream_task = asyncio.create_task(self.stream_response(user_input))
                
                try:
                    await stream_task
                except KeyboardInterrupt:
                    # Cancel the streaming task
                    stream_task.cancel()
                    try:
                        await stream_task
                    except asyncio.CancelledError:
                        pass  # Expected

            except KeyboardInterrupt:
                # Ctrl+C at prompt - show hint
                self.console.print("\n⚠️  Press Ctrl+C during streaming to cancel. Use /exit to quit", style="yellow")
                continue

            except EOFError:
                self.console.print("\n👋 Goodbye!", style="cyan")
                break

            except Exception as e:
                self.console.print(f"\n❌ Error: {e}", style="bold red")
                logger.error(f"Error in main loop: {e}", exc_info=True)


async def main():
    """Main entry point."""
    # Determine project directory (current directory)
    project_dir = Path(__file__).parent.resolve()

    # Create and run CLI
    cli = ChatCLI(project_dir)
    await cli.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {e}")
        logger.error("Fatal error", exc_info=True)
        sys.exit(1)
