"""Data models for CLI configuration and session state."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

import yaml
from pydantic import BaseModel, Field

from src.policies.hitl_config import HITLMode


class ProjectConfig(BaseModel):
    """Project configuration loaded from agent_config.yaml."""

    name: str = Field(default="Agent Project", description="Project name")
    description: str = Field(default="", description="Project description")
    version: str = Field(default="1.0.0", description="Project version")

    # Plugin configuration
    plugins_auto_discover: bool = Field(
        default=True, description="Auto-discover plugins from plugins/ folder"
    )
    plugins_paths: List[str] = Field(
        default_factory=lambda: ["plugins/"], description="Plugin search paths"
    )

    # Context configuration
    runbooks_path: Optional[str] = Field(
        default="runbooks.json", description="Path to runbooks file"
    )
    examples_path: Optional[str] = Field(
        default="examples.json", description="Path to examples file"
    )

    # Default settings
    default_hitl_mode: str = Field(
        default="guided_automation", description="Default HITL mode"
    )
    default_step_budget: int = Field(default=6, description="Default step budget")
    enable_feedback: bool = Field(
        default=True, description="Enable feedback collection"
    )
    log_level: str = Field(default="INFO", description="Logging level")

    # Data paths (optional, project-specific)
    data_paths: Dict[str, str] = Field(
        default_factory=dict, description="Project-specific data paths"
    )

    @classmethod
    def from_yaml(cls, path: Path) -> "ProjectConfig":
        """Load configuration from YAML file."""
        with open(path, "r") as f:
            data = yaml.safe_load(f)

        # Flatten nested structure if present
        config_data = {}

        if "project" in data:
            proj = data["project"]
            config_data["name"] = proj.get("name", "Agent Project")
            config_data["description"] = proj.get("description", "")
            config_data["version"] = proj.get("version", "1.0.0")

        if "plugins" in data:
            plugins = data["plugins"]
            config_data["plugins_auto_discover"] = plugins.get("auto_discover", True)
            config_data["plugins_paths"] = plugins.get("paths", ["plugins/"])

        if "context" in data:
            context = data["context"]
            config_data["runbooks_path"] = context.get("runbooks")
            config_data["examples_path"] = context.get("examples")

        if "settings" in data:
            settings = data["settings"]
            config_data["default_hitl_mode"] = settings.get(
                "default_hitl_mode", "guided_automation"
            )
            config_data["default_step_budget"] = settings.get("default_step_budget", 6)
            config_data["enable_feedback"] = settings.get("enable_feedback", True)
            config_data["log_level"] = settings.get("log_level", "INFO")

        if "data" in data:
            config_data["data_paths"] = data["data"]

        return cls(**config_data)

    @classmethod
    def from_defaults(cls, project_path: Path) -> "ProjectConfig":
        """Create default configuration for project without config file."""
        return cls(
            name=project_path.name,
            description=f"Agent project at {project_path}",
        )


@dataclass
class SessionSettings:
    """Runtime session settings (mutable during session)."""

    hitl_mode: HITLMode = HITLMode.GUIDED_AUTOMATION
    step_budget: int = 6
    enable_feedback: bool = True

    def update_hitl_mode(self, mode: str) -> bool:
        """Update HITL mode from string.

        Returns:
            True if successful, False if invalid mode
        """
        try:
            self.hitl_mode = HITLMode(mode.lower())
            return True
        except ValueError:
            return False

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for display."""
        return {
            "HITL Mode": self.hitl_mode.value.upper(),
            "Step Budget": str(self.step_budget),
            "Feedback Enabled": str(self.enable_feedback),
        }


@dataclass
class TaskRecord:
    """Record of a completed task."""

    task_id: int
    task: str
    success: bool
    duration: float
    steps_executed: int
    timestamp: str

    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for display."""
        status = "✓ Done" if self.success else "✗ Failed"
        return {
            "ID": str(self.task_id),
            "Task": self.task[:50] + "..." if len(self.task) > 50 else self.task,
            "Status": status,
            "Duration": f"{self.duration:.1f}s",
            "Steps": str(self.steps_executed),
        }


@dataclass
class SessionState:
    """Complete session state."""

    project_path: Path
    project_config: ProjectConfig
    settings: SessionSettings = field(default_factory=SessionSettings)
    task_history: List[TaskRecord] = field(default_factory=list)
    plugins_loaded: List[str] = field(default_factory=list)

    def add_task_record(self, record: TaskRecord) -> None:
        """Add task to history."""
        self.task_history.append(record)

    def get_task_count(self) -> int:
        """Get number of completed tasks."""
        return len(self.task_history)


@dataclass
class TaskConfig:
    """Configuration for a specific task."""

    task_id: str
    hitl_mode: Optional[HITLMode] = None  # None = inherit from session
    step_budget: Optional[int] = None  # None = inherit from session
    runbooks: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    task_description: Optional[str] = None
    pre_note: Optional[str] = None

    def get_effective_hitl_mode(self, session_mode: HITLMode) -> HITLMode:
        """Get effective HITL mode (task-specific or session default)."""
        return self.hitl_mode if self.hitl_mode else session_mode

    def get_effective_step_budget(self, session_budget: int) -> int:
        """Get effective step budget (task-specific or session default)."""
        return self.step_budget if self.step_budget else session_budget


__all__ = ["ProjectConfig", "SessionSettings", "TaskRecord", "SessionState", "TaskConfig"]
