"""Interactive plugin explorer with rich formatting."""

import asyncio
import json
from typing import Dict, List, Optional, Tuple

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax
from rich.text import Text

from src.cli.agent_session import AgentSession
from src.plugins.tooling_metadata import RiskLevel


class PluginExplorer:
    """Interactive plugin exploration interface."""

    def __init__(self, session: AgentSession):
        """Initialize plugin explorer.

        Args:
            session: Current agent session
        """
        self.session = session
        self.console = Console()
        self.current_level = "plugins"  # plugins, plugin, tool
        self.current_plugin = None
        self.current_tool = None
        self.search_term = None

    async def start(self) -> None:
        """Start interactive plugin explorer."""
        try:
            while True:
                # Clear screen and show current level
                self.console.clear()

                if self.current_level == "plugins":
                    if not await self._show_plugin_list():
                        break
                elif self.current_level == "plugin":
                    if not await self._show_plugin_details():
                        break
                elif self.current_level == "tool":
                    if not await self._show_tool_details():
                        break

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Explorer interrupted[/yellow]")

    async def _show_plugin_list(self) -> bool:
        """Show plugin list and handle input.

        Returns:
            False to exit, True to continue
        """
        plugins_info = self.session.get_plugins_info()

        if not plugins_info:
            self.console.print("[red]No plugins loaded[/red]")
            return False

        # Count total tools
        total_tools = sum(len(info["tools"]) for info in plugins_info.values())

        # Header
        header = Panel(
            f"🔌 Plugin Explorer ({len(plugins_info)} plugin(s), {total_tools} tool(s))",
            style="bold cyan",
        )
        self.console.print(header)
        self.console.print()

        # Plugin list
        plugin_names = list(plugins_info.keys())
        for idx, plugin_name in enumerate(plugin_names, 1):
            info = plugins_info[plugin_name]
            tool_count = len(info["tools"])

            self.console.print(f"[bold cyan][{idx}][/bold cyan] {plugin_name} ({tool_count} tools)")

            # Show description if available
            if info.get("description"):
                self.console.print(f"    {info['description']}", style="dim")

            self.console.print()

        # Commands help
        self.console.print(
            "[dim]Commands: <number> | search <term> | help | exit[/dim]"
        )
        self.console.print()

        # Get user input
        user_input = await self._get_input("plugins> ")

        if not user_input:
            return True

        # Parse command
        parts = user_input.strip().split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "exit":
            return False
        elif cmd == "help":
            await self._show_help("plugins")
            return True
        elif cmd == "search":
            if len(parts) > 1:
                self.search_term = parts[1]
                self.console.print(f"[green]Search set to: {self.search_term}[/green]")
                await asyncio.sleep(1)
            else:
                self.console.print("[red]Usage: search <term>[/red]")
                await asyncio.sleep(1)
            return True
        elif cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(plugin_names):
                self.current_plugin = plugin_names[idx]
                self.current_level = "plugin"
            else:
                self.console.print("[red]Invalid plugin number[/red]")
                await asyncio.sleep(1)
            return True
        else:
            self.console.print(f"[red]Unknown command: {cmd}[/red]")
            await asyncio.sleep(1)
            return True

    async def _show_plugin_details(self) -> bool:
        """Show plugin details and tool list.

        Returns:
            False to exit, True to continue
        """
        plugins_info = self.session.get_plugins_info()
        plugin_info = plugins_info.get(self.current_plugin)

        if not plugin_info:
            self.current_level = "plugins"
            return True

        # Header
        header = Panel(
            f"{self.current_plugin} Plugin",
            style="bold cyan",
        )
        self.console.print(header)
        self.console.print()

        # Plugin metadata
        self.console.print(f"[bold]Description:[/bold] {plugin_info.get('description', 'N/A')}")
        self.console.print(f"[bold]Tools:[/bold] {len(plugin_info['tools'])}")
        self.console.print()

        # Tools table
        table = Table(show_header=True, header_style="bold cyan", box=None)
        table.add_column("", style="cyan", width=4)
        table.add_column("Tool", style="bold")
        table.add_column("Risk", width=10)
        table.add_column("Description")

        # Filter tools if search term is active
        tools = plugin_info["tools"]
        if self.search_term:
            tools = [
                t for t in tools
                if self.search_term.lower() in t["name"].lower()
                or self.search_term.lower() in t["description"].lower()
            ]

        for idx, tool in enumerate(tools, 1):
            risk_color = self._get_risk_color(tool["risk_level"])
            desc = tool["description"][:50] + "..." if len(tool["description"]) > 50 else tool["description"]

            table.add_row(
                f"[{idx}]",
                tool["name"],
                f"[{risk_color}]{tool['risk_level']}[/{risk_color}]",
                desc,
            )

        self.console.print(table)
        self.console.print()

        # Commands help
        if self.search_term:
            self.console.print(f"[dim]🔍 Searching for: {self.search_term}[/dim]")
        self.console.print(
            "[dim]Commands: <number> | search <term> | clear | back | exit[/dim]"
        )
        self.console.print()

        # Get user input
        user_input = await self._get_input(f"{self.current_plugin}> ")

        if not user_input:
            return True

        # Parse command
        parts = user_input.strip().split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "exit":
            return False
        elif cmd == "back":
            self.current_level = "plugins"
            self.current_plugin = None
            return True
        elif cmd == "search":
            if len(parts) > 1:
                self.search_term = parts[1]
                self.console.print(f"[green]Search set to: {self.search_term}[/green]")
                await asyncio.sleep(1)
            else:
                self.console.print("[red]Usage: search <term>[/red]")
                await asyncio.sleep(1)
            return True
        elif cmd == "clear":
            self.search_term = None
            self.console.print("[green]Search cleared[/green]")
            await asyncio.sleep(1)
            return True
        elif cmd.isdigit():
            idx = int(cmd) - 1
            if 0 <= idx < len(tools):
                self.current_tool = tools[idx]["name"]
                self.current_level = "tool"
            else:
                self.console.print("[red]Invalid tool number[/red]")
                await asyncio.sleep(1)
            return True
        else:
            self.console.print(f"[red]Unknown command: {cmd}[/red]")
            await asyncio.sleep(1)
            return True

    async def _show_tool_details(self) -> bool:
        """Show detailed tool information.

        Returns:
            False to exit, True to continue
        """
        # Get tool metadata from session plugin manager
        if not self.session.plugin_manager:
            self.console.print("[red]Session not initialized[/red]")
            self.current_level = "plugin"
            return True

        manifest = self.session.plugin_manager.get_tool_manifest()

        # Find the tool
        tool_def = None
        if self.current_plugin in manifest:
            tools = manifest[self.current_plugin]
            for tool_name, definition in tools.items():
                if tool_name == self.current_tool:
                    tool_def = definition
                    break

        if not tool_def:
            self.current_level = "plugin"
            return True

        # Header
        header = Panel(
            f"{self.current_tool} ({self.current_plugin})",
            style="bold cyan",
        )
        self.console.print(header)
        self.console.print()

        # Description
        self.console.print("📝 [bold]Description:[/bold]")
        self.console.print(f"   {tool_def.description}")
        self.console.print()

        # Capabilities
        if tool_def.capabilities:
            caps = ", ".join([c.value for c in tool_def.capabilities])
            self.console.print(f"🎯 [bold]Capabilities:[/bold] {caps}")
            self.console.print()

        # Risk and approval
        risk_color = self._get_risk_color(tool_def.risk_level.value)
        self.console.print(f"⚠️  [bold]Risk Level:[/bold] [{risk_color}]{tool_def.risk_level.value}[/{risk_color}]")
        self.console.print(f"🔒 [bold]Approval:[/bold] {tool_def.approval.value}")
        self.console.print()

        self.console.print("━" * 60)
        self.console.print()

        # Inputs
        if tool_def.inputs:
            self.console.print("📥 [bold]Inputs:[/bold]")
            for input_spec in tool_def.inputs:
                required = "" if input_spec.required else " (optional)"
                self.console.print(f"   • {input_spec.name}{required}")
                self.console.print(f"     {input_spec.description}", style="dim")
            self.console.print()

        # Output
        if tool_def.output_description:
            self.console.print("📤 [bold]Output:[/bold]")
            self.console.print(f"   {tool_def.output_description}")
            self.console.print()

        # Field descriptions (schema)
        if tool_def.field_descriptions:
            self.console.print("🔍 [bold]Output Fields:[/bold]")
            for field, desc in tool_def.field_descriptions.items():
                self.console.print(f"   • {field}: {desc}", style="dim")
            self.console.print()

        # Sample output
        if tool_def.sample_output:
            self.console.print("💡 [bold]Sample Output:[/bold]")
            try:
                # Try to parse as JSON for pretty printing
                sample_json = json.loads(tool_def.sample_output)
                syntax = Syntax(
                    json.dumps(sample_json, indent=2),
                    "json",
                    theme="monokai",
                    line_numbers=False,
                )
                self.console.print(syntax)
            except:
                self.console.print(f"   {tool_def.sample_output}", style="dim")
            self.console.print()

        # Commands help
        self.console.print("[dim]Commands: back | exit[/dim]")
        self.console.print()

        # Get user input
        user_input = await self._get_input("tool> ")

        if not user_input:
            return True

        cmd = user_input.strip().lower()

        if cmd == "exit":
            return False
        elif cmd == "back":
            self.current_level = "plugin"
            self.current_tool = None
            return True
        else:
            self.console.print(f"[red]Unknown command: {cmd}[/red]")
            await asyncio.sleep(1)
            return True

    def _get_risk_color(self, risk_level: str) -> str:
        """Get color for risk level.

        Args:
            risk_level: Risk level string

        Returns:
            Rich color name
        """
        risk_colors = {
            "LOW": "green",
            "MEDIUM": "yellow",
            "HIGH": "red",
            "CRITICAL": "bold red",
        }
        return risk_colors.get(risk_level.upper(), "white")

    async def _get_input(self, prompt: str) -> str:
        """Get user input asynchronously.

        Args:
            prompt: Prompt to display

        Returns:
            User input
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, prompt)

    async def _show_help(self, level: str) -> None:
        """Show help for current level.

        Args:
            level: Current navigation level
        """
        self.console.print()
        self.console.print("[bold cyan]Help:[/bold cyan]")
        self.console.print()

        if level == "plugins":
            self.console.print("  <number>      - View plugin details")
            self.console.print("  search <term> - Search for tools")
            self.console.print("  help          - Show this help")
            self.console.print("  exit          - Exit explorer")

        await asyncio.sleep(2)


__all__ = ["PluginExplorer"]
