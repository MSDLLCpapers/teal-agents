from pydantic import BaseModel


class ConversationMessageRequest(BaseModel):
    message: str
    image_data: list[str] | str | None = None


class AgentRegistrationRequest(BaseModel):
    """Request to register or update an agent."""
    service_name: str  # The agent name (unique identifier)
    description: str  # Required for new/update
    desc_keywords: list[str] | None = None  # Optional, extracted via TF-IDF if not provided
    deployment_name: str | None = None  # Optional, uses default if not provided
    agents: list[str]  # List of agent names that should be active - agents in DB but not in this list will be soft deleted (is_active=False)
