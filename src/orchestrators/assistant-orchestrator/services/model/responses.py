from pydantic import BaseModel


class UserMessage(BaseModel):
    content: str
    recipient: str


class AgentMessage(BaseModel):
    content: str
    sender: str


class ConversationResponse(BaseModel):
    conversation_id: str
    history: list[UserMessage | AgentMessage]


class GeneralResponse(BaseModel):
    status: int
    message: str


class AuthenticationResponse(BaseModel):
    orchestrator_name: str
    user_id: str


class CreateTicketResponse(BaseModel):
    ticket: str


class VerifyTicketResponse(BaseModel):
    is_valid: bool
    user_id: str | None = None
