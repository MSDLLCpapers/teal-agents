from pydantic import BaseModel


class BaseAgent(BaseModel):
    name: str
    version: str
    description: str
