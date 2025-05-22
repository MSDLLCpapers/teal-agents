from pydantic import BaseModel


class AgentRequestEvent(BaseModel):
    session_id: str | None = None
    source: str | None = None
    request_id: str | None = None

    task_id: str
    agent_name: str
    task_goal: str


class AgentResponseEvent(BaseModel):
    task_id: str
    agent_name: str
    task_result: str


class PartialAgentResponseEvent(BaseModel):
    task_id: str
    agent_name: str
    partial_result: str
