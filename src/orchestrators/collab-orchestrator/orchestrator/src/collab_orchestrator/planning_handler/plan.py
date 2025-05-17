from enum import Enum
from typing import List

from collab_orchestrator.planning_handler.planning_agent import (
    Task,
    Step as PlanStep,
    GeneratePlanResponse,
)
from pydantic import BaseModel


class TaskStatus(Enum):
    TODO = "TODO"
    DONE = "DONE"


class ExecutableTask(BaseModel):
    task_id: str
    prerequisite_tasks: List[str]
    task_goal: str
    task_agent: str
    status: TaskStatus = TaskStatus.TODO
    result: str | None = None

    @staticmethod
    def new_from_plan_task(plan_task: Task) -> "ExecutableTask":
        return ExecutableTask(
            task_id=plan_task.task_id,
            prerequisite_tasks=plan_task.prerequisite_tasks,
            task_goal=plan_task.task_goal,
            task_agent=plan_task.task_agent,
            status=TaskStatus.TODO,
            result=None,
        )


class Step(BaseModel):
    step_number: int
    step_tasks: List[ExecutableTask]

    @staticmethod
    def new_from_plan_step(plan_step: PlanStep) -> "Step":
        return Step(
            step_number=plan_step.step_number,
            step_tasks=[
                ExecutableTask.new_from_plan_task(task) for task in plan_step.step_tasks
            ],
        )


class Plan(BaseModel):
    session_id: str | None = None
    source: str | None = None
    request_id: str | None = None

    steps: List[Step]

    @staticmethod
    def new_from_response(response: GeneratePlanResponse) -> "Plan":
        return Plan(steps=[Step.new_from_plan_step(step) for step in response.steps])
