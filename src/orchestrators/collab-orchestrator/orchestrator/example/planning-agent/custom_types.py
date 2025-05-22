from pydantic import BaseModel
from semantic_kernel.kernel_pydantic import KernelBaseModel
from sk_agents.ska_types import HistoryMessage


class Agent(BaseModel):
    name: str
    description: str


class PlanningAgentInput(KernelBaseModel):
    chat_history: list[HistoryMessage] | None = None
    overall_goal: str
    agent_list: list[Agent]


class Task(BaseModel):
    task_id: str
    prerequisite_tasks: list[str]
    task_goal: str
    task_agent: str


class Step(BaseModel):
    step_number: int
    step_tasks: list[Task]


class PlanningAgentOutput(KernelBaseModel):
    can_succeed: bool
    reasoning: str | None = None
    steps: list[Step] | None
