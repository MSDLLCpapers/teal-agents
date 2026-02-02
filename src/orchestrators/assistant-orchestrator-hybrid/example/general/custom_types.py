from typing import List

from sk_agents.ska_types import BaseInput

from semantic_kernel.kernel_pydantic import KernelBaseModel


class Agent(KernelBaseModel):
    name: str
    description: str


class GeneralInput(BaseInput):
    agents: List[Agent]
