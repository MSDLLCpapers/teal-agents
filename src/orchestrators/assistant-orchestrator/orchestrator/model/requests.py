from pydantic import BaseModel


class ConversationMessageRequest(BaseModel):
    message: str
    image_data: str | None = None
