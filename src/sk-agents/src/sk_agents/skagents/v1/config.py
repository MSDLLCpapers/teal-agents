from pydantic import BaseModel, ConfigDict


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    role: str | None = None
    model: str
    system_prompt: str
    plugins: list[str] | None = None
    remote_plugins: list[str] | None = None
