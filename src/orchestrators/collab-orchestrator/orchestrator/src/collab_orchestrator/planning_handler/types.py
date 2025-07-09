from collab_orchestrator.co_types import SpecBase


class PlanningSpec(SpecBase):
    planning_agent: str
    stream_tokens: bool = True
