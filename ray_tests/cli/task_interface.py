"""Interactive task creation and execution interface."""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.cli.agent_session import AgentSession
from src.cli.models import TaskRecord, SessionSettings, TaskConfig
from src.policies.hitl_config import HITLMode


class TaskInterface:
    """Interactive interface for creating and executing tasks."""

    def __init__(self, session: AgentSession):
        """Initialize task interface.

        Args:
            session: Current agent session
        """
        self.session = session
        self.console = Console()

        # Generate task ID
        task_num = self.session.state.get_task_count() + 1
        self.task_id = f"task_{task_num:02d}"

        # Initialize task config
        self.config = TaskConfig(task_id=self.task_id)

        # Copy loaded runbooks/examples from session
        # (User can add/remove from here without affecting session)
        config = self.session.state.project_config
        if config.runbooks_path:
            self.config.runbooks.append("wifi-rca")  # Default ID
        if config.examples_path:
            self.config.examples.append("plan-react")  # Default ID

    async def start(self) -> bool:
        """Start task interface command loop.

        Returns:
            False to exit shell, True to continue
        """
        try:
            # Show header
            self.console.clear()
            self._show_header()

            # Command loop
            while True:
                # Show current status
                self._show_status()

                # Get command
                user_input = await self._get_input(f"\n{self.task_id}> ")

                if not user_input:
                    continue

                # Parse and execute command
                should_continue = await self._handle_command(user_input.strip())

                if not should_continue:
                    break

            return True

        except KeyboardInterrupt:
            self.console.print("\n[yellow]Task interface cancelled[/yellow]")
            return True

    def _show_header(self) -> None:
        """Show task interface header."""
        header = Panel(
            f"📋 Task Interface: {self.task_id}",
            style="bold cyan",
        )
        self.console.print(header)
        self.console.print()

    def _show_status(self) -> None:
        """Show current task configuration."""
        self.console.print()
        self.console.print("[bold]Task Configuration:[/bold]")
        self.console.print("─" * 60)

        # Settings (show if overridden or inherited)
        session_mode = self.session.state.settings.hitl_mode.value
        session_budget = self.session.state.settings.step_budget

        if self.config.hitl_mode:
            self.console.print(f"  HITL Mode: {self.config.hitl_mode.value} [yellow](task-specific)[/yellow]")
        else:
            self.console.print(f"  HITL Mode: {session_mode} [dim](from session)[/dim]")

        if self.config.step_budget:
            self.console.print(f"  Step Budget: {self.config.step_budget} [yellow](task-specific)[/yellow]")
        else:
            self.console.print(f"  Step Budget: {session_budget} [dim](from session)[/dim]")

        # Context
        self.console.print(f"  Runbooks: {len(self.config.runbooks)} loaded")
        self.console.print(f"  Examples: {len(self.config.examples)} loaded")

        # Task description
        if self.config.task_description:
            desc_preview = self.config.task_description[:50] + "..." if len(self.config.task_description) > 50 else self.config.task_description
            self.console.print(f"  Description: [green]{desc_preview}[/green]")
        else:
            self.console.print(f"  Description: [red]Not set[/red]")

        self.console.print()
        self.console.print("[dim]Commands: /settings, /runbooks, /examples, /desc, /run, /status, /cancel[/dim]")

    async def _handle_command(self, user_input: str) -> bool:
        """Handle task interface command.

        Args:
            user_input: User input string

        Returns:
            True to continue loop, False to exit
        """
        if not user_input.startswith('/'):
            self.console.print("[red]Commands must start with /[/red]")
            self.console.print("[dim]Available: /settings, /runbooks, /examples, /run, /status, /cancel[/dim]")
            return True

        parts = user_input[1:].split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else None

        if cmd == "settings":
            await self._handle_settings(args)
        elif cmd == "runbooks":
            await self._manage_runbooks()
        elif cmd == "examples":
            await self._manage_examples()
        elif cmd == "desc":
            await self._handle_description()
        elif cmd == "run":
            executed = await self._execute_task()
            return not executed  # Exit task interface after execution
        elif cmd == "status":
            # Status already shown, just continue
            pass
        elif cmd == "cancel":
            self.console.print("[yellow]Task cancelled[/yellow]")
            return False
        else:
            self.console.print(f"[red]Unknown command: /{cmd}[/red]")

        return True

    async def _handle_settings(self, args: Optional[str]) -> None:
        """Handle settings command.

        Args:
            args: Arguments string (key=value or None)
        """
        if not args:
            # Show current settings with options
            self.console.print()
            self.console.print("[bold]Task Settings:[/bold]")
            self.console.print("─" * 60)

            session_settings = self.session.state.settings

            self.console.print(f"  hitl_mode: {self.config.get_effective_hitl_mode(session_settings.hitl_mode).value}")
            if self.config.hitl_mode:
                self.console.print("    [yellow](task-specific override)[/yellow]")
            else:
                self.console.print("    [dim](inherited from session)[/dim]")

            self.console.print(f"  step_budget: {self.config.get_effective_step_budget(session_settings.step_budget)}")
            if self.config.step_budget:
                self.console.print("    [yellow](task-specific override)[/yellow]")
            else:
                self.console.print("    [dim](inherited from session)[/dim]")

            self.console.print()
            self.console.print("[bold]Available HITL Modes:[/bold]")
            self.console.print("  [0] autonomous       - No approvals (testing)")
            self.console.print("  [1] strategic_review - Review plans only")
            self.console.print("  [2] guided_automation - Plans + high-risk (DEFAULT)")
            self.console.print("  [3] manual           - Approve everything")

            self.console.print()
            self.console.print("[dim]Usage: /settings hitl_mode=<mode>[/dim]")
            self.console.print("[dim]       /settings step_budget=<number>[/dim]")
            return

        # Parse key=value
        if "=" not in args:
            self.console.print("[red]Invalid format. Use: /settings key=value[/red]")
            return

        key, value = args.split("=", 1)
        key = key.strip().lower()
        value = value.strip()

        if key == "hitl_mode":
            try:
                self.config.hitl_mode = HITLMode(value.lower())
                self.console.print(f"[green]✓ Task hitl_mode set to: {value}[/green]")
            except ValueError:
                self.console.print(f"[red]Invalid HITL mode: {value}[/red]")
                self.console.print("[dim]Valid: autonomous, strategic_review, guided_automation, manual[/dim]")

        elif key == "step_budget":
            try:
                budget = int(value)
                if budget > 0:
                    self.config.step_budget = budget
                    self.console.print(f"[green]✓ Task step_budget set to: {budget}[/green]")
                else:
                    self.console.print("[red]Step budget must be positive[/red]")
            except ValueError:
                self.console.print(f"[red]Invalid number: {value}[/red]")

        else:
            self.console.print(f"[red]Unknown setting: {key}[/red]")

    async def _manage_runbooks(self) -> None:
        """Manage runbooks subshell."""
        while True:
            self.console.print()
            self.console.print("─" * 60)
            self.console.print(f"[bold cyan]Runbook Management ({self.task_id})[/bold cyan]")
            self.console.print("─" * 60)

            # Show loaded runbooks
            if self.config.runbooks:
                self.console.print("[bold]Loaded Runbooks:[/bold]")
                for idx, rb_id in enumerate(self.config.runbooks, 1):
                    self.console.print(f"  [{idx}] ✓ {rb_id}")
            else:
                self.console.print("[dim]No runbooks loaded[/dim]")

            self.console.print()
            self.console.print("[dim]Commands: load <path>, remove <id>, list, back[/dim]")

            user_input = await self._get_input("\nrunbooks> ")

            if not user_input:
                continue

            parts = user_input.strip().split(maxsplit=1)
            cmd = parts[0].lower()

            if cmd == "back":
                break
            elif cmd == "list":
                continue  # Just redisplay
            elif cmd == "load":
                if len(parts) > 1:
                    rb_id = parts[1]
                    self.config.runbooks.append(rb_id)
                    self.console.print(f"[green]✓ Added runbook: {rb_id}[/green]")
                else:
                    self.console.print("[red]Usage: load <runbook_id>[/red]")
            elif cmd == "remove":
                if len(parts) > 1:
                    rb_id = parts[1]
                    if rb_id in self.config.runbooks:
                        self.config.runbooks.remove(rb_id)
                        self.console.print(f"[green]✓ Removed runbook: {rb_id}[/green]")
                    else:
                        self.console.print(f"[red]Runbook not found: {rb_id}[/red]")
                else:
                    self.console.print("[red]Usage: remove <runbook_id>[/red]")
            else:
                self.console.print(f"[red]Unknown command: {cmd}[/red]")

            await asyncio.sleep(0.5)

    async def _manage_examples(self) -> None:
        """Manage examples subshell."""
        while True:
            self.console.print()
            self.console.print("─" * 60)
            self.console.print(f"[bold cyan]Examples Management ({self.task_id})[/bold cyan]")
            self.console.print("─" * 60)

            # Show loaded examples
            if self.config.examples:
                self.console.print("[bold]Loaded Examples:[/bold]")
                for idx, ex_id in enumerate(self.config.examples, 1):
                    self.console.print(f"  [{idx}] ✓ {ex_id}")
            else:
                self.console.print("[dim]No examples loaded[/dim]")

            self.console.print()
            self.console.print("[dim]Commands: load <id>, remove <id>, list, back[/dim]")

            user_input = await self._get_input("\nexamples> ")

            if not user_input:
                continue

            parts = user_input.strip().split(maxsplit=1)
            cmd = parts[0].lower()

            if cmd == "back":
                break
            elif cmd == "list":
                continue  # Just redisplay
            elif cmd == "load":
                if len(parts) > 1:
                    ex_id = parts[1]
                    self.config.examples.append(ex_id)
                    self.console.print(f"[green]✓ Added examples: {ex_id}[/green]")
                else:
                    self.console.print("[red]Usage: load <example_id>[/red]")
            elif cmd == "remove":
                if len(parts) > 1:
                    ex_id = parts[1]
                    if ex_id in self.config.examples:
                        self.config.examples.remove(ex_id)
                        self.console.print(f"[green]✓ Removed examples: {ex_id}[/green]")
                    else:
                        self.console.print(f"[red]Examples not found: {ex_id}[/red]")
                else:
                    self.console.print("[red]Usage: remove <example_id>[/red]")
            else:
                self.console.print(f"[red]Unknown command: {cmd}[/red]")

            await asyncio.sleep(0.5)

    async def _execute_task(self) -> bool:
        """Execute the configured task.

        Returns:
            True if executed, False if cancelled
        """
        # Confirm or update description if already set
        if self.config.task_description:
            self.console.print()
            self.console.print("[bold]Current Description:[/bold]")
            self.console.print(f"  {self.config.task_description}")
            self.console.print()

            confirm = await self._get_input("Use this description? [Y/n]: ")

            if confirm and confirm.lower() in ["n", "no"]:
                self.console.print()
                self.console.print("[bold]Enter New Description:[/bold]")
                self.console.print("[dim]Type description or use Ctrl+D for multi-line:[/dim]")
                self.console.print()

                lines = []
                try:
                    while True:
                        line = await self._get_input("> ")
                        lines.append(line)
                except EOFError:
                    desc = "\n".join(lines).strip()
                    if desc:
                        self.config.task_description = desc
                        self.console.print(f"\n[green]✓ Description updated[/green]")
                    else:
                        self.console.print("\n[yellow]Keeping original description[/yellow]")
                except KeyboardInterrupt:
                    self.console.print("\n[yellow]Keeping original description[/yellow]")
        else:
            # No description set - get one
            self.console.print()
            self.console.print("[bold]Enter Task Description:[/bold]")
            self.console.print("[dim]Type description or use Ctrl+D for multi-line (Ctrl+C to cancel):[/dim]")
            self.console.print()

            lines = []
            try:
                while True:
                    line = await self._get_input("> ")
                    lines.append(line)
            except EOFError:
                desc = "\n".join(lines).strip()
                if desc:
                    self.config.task_description = desc
                else:
                    self.console.print("\n[red]Description required[/red]")
                    return False
            except KeyboardInterrupt:
                self.console.print("\n[yellow]Execution cancelled[/yellow]")
                return False

        # Get pre-run note if not set
        if not self.config.pre_note:
            self.console.print()
            self.console.print("[bold]Pre-run Note (optional):[/bold]")
            self.console.print("[dim]Add guidance for agent (press Enter to skip):[/dim]")
            self.console.print()

            note_input = await self._get_input("> ")

            if note_input and note_input.strip():
                self.config.pre_note = note_input.strip()

        # Show execution summary
        self.console.print()
        self.console.print("[bold]Ready to Execute:[/bold]")
        self.console.print("─" * 60)
        self.console.print(f"  Task ID: {self.task_id}")
        self.console.print(f"  Description: {self.config.task_description[:60]}...")

        effective_mode = self.config.get_effective_hitl_mode(self.session.state.settings.hitl_mode)
        effective_budget = self.config.get_effective_step_budget(self.session.state.settings.step_budget)

        self.console.print(f"  HITL Mode: {effective_mode.value}")
        self.console.print(f"  Step Budget: {effective_budget}")
        self.console.print(f"  Runbooks: {len(self.config.runbooks)}")
        self.console.print(f"  Examples: {len(self.config.examples)}")
        self.console.print()

        confirm = await self._get_input("Execute this task? [Y/n]: ")

        if confirm and confirm.lower() in ["n", "no"]:
            self.console.print("[yellow]Execution cancelled[/yellow]")
            return False

        # Create runner for this task
        try:
            runner = await self.session.create_task_runner(self.task_id, self.config)
        except RuntimeError as e:
            self.console.print(f"[red]Error:[/red] {str(e)}")
            return False

        # Add pre-run note to runner
        if self.config.pre_note:
            runner.add_note(self.config.pre_note)

        # Show execution header
        self.console.print()
        self.console.print("=" * 70)
        self.console.print(f"🚀 Executing Task: {self.task_id}")
        self.console.print("=" * 70)
        self.console.print()

        # Execute with task-specific runner
        # The ConsoleApprovalService will prompt LIVE during execution!
        result = await self.session.run_task_with_runner(
            self.task_id,
            self.config.task_description,
            hints=None
        )

        # Display comprehensive results
        self._display_results(result)

        # Get post-run feedback
        self.console.print()
        self.console.print("[bold]Post-run Feedback (optional):[/bold]")
        feedback = await self._get_input("> ")

        if feedback and feedback.strip():
            runner.add_feedback(feedback.strip())
            self.console.print("[green]✓ Feedback recorded[/green]")

        self.console.print()
        self.console.print("=" * 70)
        self.console.print(f"✓ Task {self.task_id} completed and saved to history")
        self.console.print("=" * 70)
        self.console.print()

        # Ask if user wants to cleanup runner
        cleanup = await self._get_input("Cleanup task runner? [Y/n]: ")
        if not cleanup or cleanup.lower() not in ["n", "no"]:
            await self.session.cleanup_task_runner(self.task_id)
            self.console.print(f"[green]✓ Runner cleaned up[/green]")
        else:
            self.console.print(f"[dim]Runner kept active (use '/task cleanup {self.task_id}' later)[/dim]")

        self.console.print()

        # Wait before returning to main shell
        await self._get_input("Press Enter to return to main shell...")

        return True

    def _display_results(self, result) -> None:
        """Display comprehensive task results.

        Args:
            result: AgentResult from execution
        """
        self.console.print()
        self.console.print("=" * 70)
        self.console.print("📊 EXECUTION RESULTS")
        self.console.print("=" * 70)
        self.console.print()

        # Strategic Plan
        if result.strategic_plan:
            self.console.print("[bold cyan]=== Strategic Plan ===[/bold cyan]")
            self.console.print(f"[bold]Goal:[/bold] {result.strategic_plan.goal}")
            self.console.print(f"[bold]Rationale:[/bold] {result.strategic_plan.rationale}")
            self.console.print()
            self.console.print("[bold]Steps:[/bold]")
            for step in result.strategic_plan.steps:
                self.console.print(f"  {step.step_number}. {step.title}")
                self.console.print(f"     Capability: {step.required_capability}", style="dim")
                self.console.print(f"     Success: {step.success_criteria}", style="dim")
            self.console.print()

        # Tactical Plan
        self.console.print("[bold cyan]=== Tactical Plan ===[/bold cyan]")
        for step in result.tactical_plan:
            status_icon = "✓" if step.status.value == "ready" else "⚠"
            tool_info = f"{step.plugin_name}.{step.tool_name}" if step.plugin_name else "No tool"
            self.console.print(f"  {status_icon} Step {step.step_number}: {step.title}")
            self.console.print(f"     Tool: {tool_info} ({step.status.value})", style="dim")
            if step.human_override:
                self.console.print(f"     Note: {step.human_override}", style="yellow")
        self.console.print()

        # Execution Trace
        if result.execution_trace:
            self.console.print("[bold cyan]=== Execution Trace ===[/bold cyan]")
            for trace in result.execution_trace:
                self.console.print(f"\n[bold]Step {trace.sequence}:[/bold]")
                self.console.print(f"  💭 Thought: {trace.thought}")
                self.console.print(f"  🔧 Action: {trace.action}")
                obs_preview = trace.observation[:200] + "..." if len(trace.observation) > 200 else trace.observation
                self.console.print(f"  📊 Observation: {obs_preview}")
                if trace.divergence:
                    self.console.print(
                        f"  ⚠️  Divergence ({trace.divergence.severity.value}): {trace.divergence.reason}",
                        style="yellow",
                    )
            self.console.print()

        # Final Response
        self.console.print("[bold cyan]=== Final Response ===[/bold cyan]")
        self.console.print(result.final_response)
        self.console.print()

        # Summary
        success_icon = "✅" if result.success else "❌"
        self.console.print(f"{success_icon} Execution: {result.steps_executed}/{result.steps_total} steps")

    async def _handle_description(self) -> None:
        """Handle multi-line description input."""
        self.console.print()
        self.console.print("[bold]Enter Task Description:[/bold]")
        self.console.print("[dim]Enter multi-line description. Press Ctrl+D when done, Ctrl+C to cancel.[/dim]")
        self.console.print()

        lines = []
        try:
            while True:
                line = await self._get_input("> ")
                lines.append(line)
        except EOFError:
            # Ctrl+D pressed - end input
            desc = "\n".join(lines).strip()
            if desc:
                self.config.task_description = desc
                line_count = len([l for l in lines if l.strip()])
                self.console.print(f"\n[green]✓ Description saved ({line_count} lines)[/green]")
            else:
                self.console.print("\n[yellow]No description entered[/yellow]")
        except KeyboardInterrupt:
            self.console.print("\n[yellow]Description input cancelled[/yellow]")

    async def _get_input(self, prompt: str) -> str:
        """Get user input asynchronously.

        Args:
            prompt: Prompt to display

        Returns:
            User input
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, input, prompt)


class TaskManager:
    """Manages task history and retrieval."""

    def __init__(self, session: AgentSession):
        """Initialize task manager.

        Args:
            session: Current agent session
        """
        self.session = session
        self.console = Console()

    async def list_tasks(self) -> None:
        """Display enhanced list of active and completed tasks."""
        active_tasks = self.session.get_active_tasks()
        completed_tasks = self.session.state.task_history

        total_active = len(active_tasks)
        total_completed = len(completed_tasks)

        # Header
        header = Panel(
            f"📋 Task Management ({total_active} active, {total_completed} completed)",
            style="bold cyan",
        )
        self.console.print(header)
        self.console.print()

        # Active tasks
        if active_tasks:
            self.console.print("[bold cyan]Active Tasks (runners in memory):[/bold cyan]")
            self.console.print("━" * 60)
            for task_id in active_tasks:
                # Find task info from history if it exists
                task_info = next(
                    (t for t in completed_tasks if f"task_{t.task_id:02d}" == task_id),
                    None
                )
                if task_info:
                    desc = task_info.task[:30] + "..." if len(task_info.task) > 30 else task_info.task
                    self.console.print(f"  {task_id:10s} {desc:35s} [green][🟢 Active][/green]")
                else:
                    self.console.print(f"  {task_id:10s} [dim]Configuration in progress[/dim]  [yellow][⚙️ Setup][/yellow]")
            self.console.print()

        # Completed tasks
        if completed_tasks:
            self.console.print("[bold cyan]Completed Tasks:[/bold cyan]")
            self.console.print("━" * 60)

            # Create table
            table = Table(show_header=True, header_style="bold cyan", box=None)
            table.add_column("ID", style="cyan", width=10)
            table.add_column("Task", style="bold")
            table.add_column("Status", width=12)
            table.add_column("Duration", width=10)
            table.add_column("Steps", width=8)

            for record in completed_tasks[-10:]:  # Last 10
                status = "[green]✓ Success[/green]" if record.success else "[red]✗ Failed[/red]"
                task_preview = record.task[:35] + "..." if len(record.task) > 35 else record.task

                table.add_row(
                    f"task_{record.task_id:02d}",
                    task_preview,
                    status,
                    f"{record.duration:.1f}s",
                    str(record.steps_executed),
                )

            self.console.print(table)
            self.console.print()

        # Show commands
        self.console.print("[dim]Commands: /task browse | /task status | /task cleanup <id> | /task cleanup-completed[/dim]")
        self.console.print()

    async def show_status_dashboard(self) -> None:
        """Display resource usage dashboard."""
        active_count = len(self.session.get_active_tasks())
        max_tasks = self.session.MAX_CONCURRENT_TASKS
        completed_count = len(self.session.state.task_history)

        # Calculate success rate
        if completed_count > 0:
            success_count = sum(1 for t in self.session.state.task_history if t.success)
            success_rate = (success_count / completed_count) * 100
        else:
            success_rate = 0

        self.console.print()
        self.console.print("=" * 60)
        self.console.print("[bold cyan]📊 Task Status Dashboard[/bold cyan]")
        self.console.print("=" * 60)
        self.console.print()

        # Resource usage
        self.console.print("[bold]Resource Usage:[/bold]")
        self.console.print(f"  Active Runners: {active_count}/{max_tasks}")
        if active_count >= max_tasks:
            self.console.print("    [red]⚠️  At maximum capacity[/red]")

        est_memory = active_count * 200  # Rough estimate
        self.console.print(f"  Memory Estimate: ~{est_memory}MB ({active_count} runners)")
        self.console.print()

        # Task statistics
        self.console.print("[bold]Task Statistics:[/bold]")
        self.console.print(f"  Total Created: {completed_count}")
        self.console.print(f"  Active: {active_count}")
        self.console.print(f"  Success Rate: {success_rate:.0f}%")
        self.console.print()

        # Active tasks detail
        if active_count > 0:
            self.console.print("[bold]Active Tasks:[/bold]")
            for task_id in self.session.get_active_tasks():
                self.console.print(f"  • {task_id}")
            self.console.print()

        # Recommendations
        if active_count >= max_tasks:
            self.console.print("[yellow]Recommendations:[/yellow]")
            self.console.print("  ⚠️  Maximum tasks reached - cleanup to create new tasks")
            self.console.print(f"     Use: /task cleanup <id>")
        elif active_count > 0:
            self.console.print("[dim]Tip: Use /task cleanup-completed to free resources[/dim]")

        self.console.print("=" * 60)
        self.console.print()

    async def cleanup_completed_tasks(self) -> None:
        """Cleanup runners for all completed tasks."""
        completed_ids = [f"task_{t.task_id:02d}" for t in self.session.state.task_history]
        active_tasks = self.session.get_active_tasks()

        # Find active tasks that are completed
        to_cleanup = [tid for tid in active_tasks if tid in completed_ids]

        if not to_cleanup:
            self.console.print("[dim]No completed tasks have active runners[/dim]")
            return

        self.console.print(f"\n[yellow]Found {len(to_cleanup)} completed task(s) with active runners[/yellow]")
        for tid in to_cleanup:
            self.console.print(f"  - {tid}")
        self.console.print()

        confirm = input("Cleanup these runners? [Y/n]: ")
        if confirm and confirm.lower() in ["n", "no"]:
            self.console.print("[yellow]Cleanup cancelled[/yellow]")
            return

        # Cleanup each
        cleaned = 0
        for task_id in to_cleanup:
            if await self.session.cleanup_task_runner(task_id):
                cleaned += 1

        self.console.print(f"\n[green]✓ Cleaned up {cleaned} runner(s)[/green]")

    async def cleanup_all_tasks(self) -> None:
        """Cleanup all task runners (with confirmation)."""
        active_tasks = self.session.get_active_tasks()

        if not active_tasks:
            self.console.print("[dim]No active runners to cleanup[/dim]")
            return

        self.console.print(f"\n[red]⚠️  This will cleanup ALL {len(active_tasks)} active runner(s)![/red]")
        for tid in active_tasks:
            self.console.print(f"  - {tid}")
        self.console.print()

        confirm = input("Are you sure? Type 'yes' to confirm: ")
        if confirm.lower() != "yes":
            self.console.print("[yellow]Cleanup cancelled[/yellow]")
            return

        # Cleanup all
        for task_id in list(active_tasks):
            await self.session.cleanup_task_runner(task_id)

        self.console.print(f"\n[green]✓ Cleaned up all {len(active_tasks)} runner(s)[/green]")


__all__ = ["TaskInterface", "TaskManager"]
