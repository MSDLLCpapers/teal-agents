"""Direct tool calling interface with @ commands."""

import asyncio
import json
import re
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from src.cli.agent_session import AgentSession


class ToolCaller:
    """Handles direct tool calls with @ syntax."""

    def __init__(self, session: AgentSession):
        """Initialize tool caller.

        Args:
            session: Current agent session
        """
        self.session = session
        self.console = Console()

    async def execute(self, command: str) -> bool:
        """Execute a tool call command.

        Args:
            command: Command string starting with @

        Returns:
            True to continue session, False to exit
        """
        # Remove @ prefix
        command = command[1:].strip()

        # Check for special commands
        if command.lower() in ["list", "help"]:
            await self._show_available_tools()
            return True

        # Parse tool call
        try:
            tool_spec, params, show_help = self._parse_command(command)
        except ValueError as e:
            self.console.print(f"[red]Error:[/red] {str(e)}")
            self.console.print("[dim]Usage: @PluginName.tool_name [key=value ...] [--help][/dim]")
            return True

        # Show help if requested
        if show_help:
            await self._show_tool_help(tool_spec)
            return True

        # Execute the tool
        await self._execute_tool(tool_spec, params)
        return True

    def _parse_command(self, command: str) -> Tuple[str, Dict[str, str], bool]:
        """Parse tool call command.

        Args:
            command: Command string without @ prefix

        Returns:
            Tuple of (tool_spec, params, show_help)

        Raises:
            ValueError: If command format is invalid
        """
        # Check for --help flag
        show_help = False
        if "--help" in command:
            command = command.replace("--help", "").strip()
            show_help = True

        # Split into tool spec and parameters
        parts = command.split()
        if not parts:
            raise ValueError("Tool name required")

        tool_spec = parts[0]

        # Validate tool spec format (PluginName.tool_name)
        if "." not in tool_spec:
            raise ValueError(
                f"Invalid tool format: {tool_spec}. Use: PluginName.tool_name"
            )

        # Parse parameters (key=value pairs)
        params = {}
        for part in parts[1:]:
            if "=" in part:
                key, value = part.split("=", 1)
                params[key.strip()] = value.strip()
            else:
                raise ValueError(f"Invalid parameter format: {part}. Use: key=value")

        return tool_spec, params, show_help

    async def _execute_tool(self, tool_spec: str, params: Dict[str, str]) -> None:
        """Execute a tool with parameters.

        Args:
            tool_spec: Tool specification (PluginName.tool_name)
            params: Parameters dictionary
        """
        plugin_name, tool_name = tool_spec.split(".", 1)

        # Get plugin manager and manifest from session
        if not self.session.plugin_manager:
            self.console.print("[red]Error:[/red] Session not initialized")
            return

        manifest = self.session.plugin_manager.get_tool_manifest()

        # Check if plugin exists
        if plugin_name not in manifest:
            self.console.print(f"[red]Error:[/red] Plugin '{plugin_name}' not found")
            self._suggest_plugins(manifest)
            return

        # Check if tool exists
        if tool_name not in manifest[plugin_name]:
            self.console.print(
                f"[red]Error:[/red] Tool '{tool_name}' not found in plugin '{plugin_name}'"
            )
            self._suggest_tools(plugin_name, manifest[plugin_name])
            return

        # Get the plugin instance from session
        plugin = self.session.plugin_manager.get_plugin(plugin_name)
        if not plugin:
            self.console.print(f"[red]Error:[/red] Could not load plugin '{plugin_name}'")
            return

        # Get the tool function
        tool_func = getattr(plugin, tool_name + "_async", None)
        if not tool_func:
            tool_func = getattr(plugin, tool_name, None)

        if not tool_func or not callable(tool_func):
            self.console.print(f"[red]Error:[/red] Tool function not found: {tool_name}")
            return

        # Show execution header
        self.console.print()
        header = Panel(
            f"🔧 Executing: {plugin_name}.{tool_name}",
            style="bold cyan",
        )
        self.console.print(header)
        self.console.print()

        # Execute the tool
        try:
            # Call the tool with parameters
            if asyncio.iscoroutinefunction(tool_func):
                result = await tool_func(**params)
            else:
                result = tool_func(**params)

            # Display result
            self._display_result(result)

        except TypeError as e:
            # Parameter error - show what parameters are available
            self.console.print(f"[red]Parameter Error:[/red] {str(e)}")
            self.console.print()
            await self._show_tool_help(tool_spec)

        except Exception as e:
            # Other execution error
            self.console.print(f"[red]Execution Error:[/red] {str(e)}")
            self.console.print()

    def _display_result(self, result: str) -> None:
        """Display tool execution result.

        Args:
            result: Tool result string (usually JSON)
        """
        self.console.print("[bold]Result:[/bold]")
        self.console.print()

        try:
            # Try to parse as JSON for pretty printing
            result_json = json.loads(result)

            # Check if it's a success/error response
            if isinstance(result_json, dict):
                if result_json.get("success"):
                    self.console.print("✅ [green]Success[/green]")
                else:
                    self.console.print("❌ [red]Failed[/red]")

                # Show main result
                if "result" in result_json:
                    syntax = Syntax(
                        json.dumps(result_json["result"], indent=2),
                        "json",
                        theme="monokai",
                        line_numbers=False,
                    )
                    self.console.print(syntax)
                else:
                    # Show full response
                    syntax = Syntax(
                        json.dumps(result_json, indent=2),
                        "json",
                        theme="monokai",
                        line_numbers=False,
                    )
                    self.console.print(syntax)
            else:
                # Non-dict JSON
                syntax = Syntax(
                    json.dumps(result_json, indent=2),
                    "json",
                    theme="monokai",
                    line_numbers=False,
                )
                self.console.print(syntax)

        except json.JSONDecodeError:
            # Not JSON, display as text
            self.console.print(result)

        self.console.print()

    async def _show_tool_help(self, tool_spec: str) -> None:
        """Show detailed help for a tool.

        Args:
            tool_spec: Tool specification (PluginName.tool_name)
        """
        plugin_name, tool_name = tool_spec.split(".", 1)

        # Get tool metadata from session plugin manager
        if not self.session.plugin_manager:
            self.console.print("[red]Error:[/red] Session not initialized")
            return

        manifest = self.session.plugin_manager.get_tool_manifest()

        if plugin_name not in manifest or tool_name not in manifest[plugin_name]:
            self.console.print(f"[red]Tool not found:[/red] {tool_spec}")
            return

        tool_def = manifest[plugin_name][tool_name]

        # Display tool info (similar to plugin explorer)
        header = Panel(
            f"{tool_name} ({plugin_name})",
            style="bold cyan",
        )
        self.console.print(header)
        self.console.print()

        # Description
        self.console.print("📝 [bold]Description:[/bold]")
        self.console.print(f"   {tool_def.description}")
        self.console.print()

        # Risk and approval
        risk_colors = {
            "LOW": "green",
            "MEDIUM": "yellow",
            "HIGH": "red",
            "CRITICAL": "bold red",
        }
        risk_color = risk_colors.get(tool_def.risk_level.value, "white")
        self.console.print(f"⚠️  [bold]Risk Level:[/bold] [{risk_color}]{tool_def.risk_level.value}[/{risk_color}]")
        self.console.print()

        # Parameters
        if tool_def.inputs:
            self.console.print("📥 [bold]Parameters:[/bold]")
            for input_spec in tool_def.inputs:
                required = "" if input_spec.required else " (optional)"
                self.console.print(f"   • {input_spec.name}{required}")
                self.console.print(f"     {input_spec.description}", style="dim")
            self.console.print()

            # Usage example
            self.console.print("[bold]Usage:[/bold]")
            param_examples = " ".join(
                [f"{inp.name}=value" for inp in tool_def.inputs if inp.required]
            )
            self.console.print(f"   @{plugin_name}.{tool_name} {param_examples}", style="cyan")
        else:
            self.console.print("📥 [bold]Parameters:[/bold] None")
            self.console.print()
            self.console.print("[bold]Usage:[/bold]")
            self.console.print(f"   @{plugin_name}.{tool_name}", style="cyan")

        self.console.print()

    async def _show_available_tools(self) -> None:
        """Show list of all available tools."""
        plugins_info = self.session.get_plugins_info()

        if not plugins_info:
            self.console.print("[red]No plugins loaded[/red]")
            return

        header = Panel(
            "🔧 Available Tools for Direct Calling",
            style="bold cyan",
        )
        self.console.print(header)
        self.console.print()

        for plugin_name, info in plugins_info.items():
            self.console.print(f"[bold cyan]{plugin_name}:[/bold cyan]")
            for tool in info["tools"]:
                risk_colors = {
                    "LOW": "green",
                    "MEDIUM": "yellow",
                    "HIGH": "red",
                    "CRITICAL": "bold red",
                }
                risk_color = risk_colors.get(tool["risk_level"], "white")
                self.console.print(
                    f"  @{plugin_name}.{tool['name']:25s} [{risk_color}]{tool['risk_level']}[/{risk_color}]"
                )
            self.console.print()

        self.console.print("[dim]Usage: @PluginName.tool_name [key=value ...] [--help][/dim]")
        self.console.print()

    def _suggest_plugins(self, manifest: Dict) -> None:
        """Suggest available plugins.

        Args:
            manifest: Tool manifest
        """
        self.console.print()
        self.console.print("[yellow]Available plugins:[/yellow]")
        for plugin_name in manifest.keys():
            self.console.print(f"  - {plugin_name}")
        self.console.print()

    def _suggest_tools(self, plugin_name: str, tools: Dict) -> None:
        """Suggest available tools in a plugin.

        Args:
            plugin_name: Plugin name
            tools: Tools dictionary
        """
        self.console.print()
        self.console.print(f"[yellow]Available tools in {plugin_name}:[/yellow]")
        for tool_name in tools.keys():
            self.console.print(f"  - @{plugin_name}.{tool_name}")
        self.console.print()


__all__ = ["ToolCaller"]
