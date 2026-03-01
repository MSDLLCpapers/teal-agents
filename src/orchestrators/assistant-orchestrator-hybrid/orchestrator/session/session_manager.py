import abc

from pydantic import BaseModel

from model.requests import ConversationMessageRequest


class SessionData(BaseModel):
    conversation_id: str
    user_id: str
    request: ConversationMessageRequest
    authorization: str | None = None


class AbstractSessionManager(abc.ABC):
    """
    Abstract base class for session management.
    """

    @abc.abstractmethod
    async def add_session(self, session_id: str, data: SessionData) -> None:
        """
        Asynchronously adds or updates session data for a given session ID.

        Args:
            session_id (str): The unique identifier for the session.
            data (SessionData): The data to store for the session.
        """
        pass

    @abc.abstractmethod
    async def get_session(self, session_id: str) -> SessionData | None:
        """
        Asynchronously retrieves session data for a given session ID.

        Args:
            session_id (str): The unique identifier for the session.

        Returns:
            Optional[SessionData]: The session data if found, otherwise None.
        """
        pass

    @abc.abstractmethod
    async def delete_session(self, session_id: str) -> None:
        """
        Asynchronously deletes session data for a given session ID.

        Args:
            session_id (str): The unique identifier for the session to delete.
        """
        pass
