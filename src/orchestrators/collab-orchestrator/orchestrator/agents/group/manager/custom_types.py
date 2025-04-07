from enum import Enum
from typing import List

from sk_agents.ska_types import HistoryMessage
from pydantic import BaseModel
from semantic_kernel.kernel_pydantic import KernelBaseModel


class Agent(BaseModel):
    name: str
    description: str


class ConversationMessage(BaseModel):
    task_id: str
    agent_name: str
    instructions: str
    result: str


class ManagerInput(KernelBaseModel):
    chat_history: List[HistoryMessage] | None = None
    overall_goal: str
    agent_list: List[Agent]
    conversation: List[ConversationMessage] | None = None


class Action(Enum):
    PROVIDE_RESULT = "provide_result"
    ABORT = "abort"
    ASSIGN_NEW_TASK = "assign_new_task"


class ResultOutput(BaseModel):
    result_task_id: str
    result: str


class AbortOutput(BaseModel):
    abort_reason: str


class AssignTaskOutput(BaseModel):
    task_id: str
    agent_name: str
    instructions: str


class ManagerOutput(KernelBaseModel):
    next_action: Action
    action_detail: ResultOutput | AbortOutput | AssignTaskOutput
