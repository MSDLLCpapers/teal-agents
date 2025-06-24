import logging

from .session_manager import AbstractSessionManager, SessionData

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class InMemorySessionManager(AbstractSessionManager):
    """
    An in-memory implementation of the AbstractSessionManager where
    session data is stored in a Python dictionary.
    This is for development and testing, but not for production
    environments requiring persistence or scaling.
    """

    def __init__(self):
        self._session_cache: dict[str, SessionData] = {}
        logger.info("InMemorySessionManager initialized.")

    async def add_session(self, session_id: str, data: SessionData) -> None:
        """
        Adds or updates session data in the in-memory cache.

        Args:
            session_id (str): The unique identifier for the session.
            data (SessionData): The data to store for the session.
        """
        self._session_cache[session_id] = data
        logger.info(f"Session '{session_id}' added/updated in memory.")

    async def get_session(self, session_id: str) -> SessionData | None:
        """
        Retrieves session data from the in-memory cache.

        Args:
            session_id (str): The unique identifier for the session.

        Returns:
            Optional[SessionData]: The session data if found, otherwise None.
        """
        session_data = self._session_cache.get(session_id)
        if session_data:
            logger.info(f"Session '{session_id}' retrieved from memory.")
        else:
            logger.info(f"Session '{session_id}' not found in memory.")
        return session_data

    async def delete_session(self, session_id: str) -> None:
        """
        Deletes session data from the in-memory cache.

        Args:
            session_id (str): The unique identifier for the session to delete.
        """
        if session_id in self._session_cache:
            del self._session_cache[session_id]
            logger.info(f"Session '{session_id}' deleted from memory.")
        else:
            logger.info(f"Session '{session_id}' not found in memory, nothing to delete.")
