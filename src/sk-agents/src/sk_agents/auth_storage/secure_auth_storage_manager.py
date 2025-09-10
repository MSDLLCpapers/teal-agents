from abc import ABC, abstractmethod

from sk_agents.auth_storage.models import AuthData


class SecureAuthStorageManager(ABC):
    @abstractmethod
    def store(self, user_id: str, key: str, data: AuthData) -> None:
        """Stores authorization data for a given user and key."""
        pass

    @abstractmethod
    def retrieve(self, user_id: str, key: str) -> AuthData | None:
        """Retrieves authorization data for a given user and key."""
        pass

    @abstractmethod
    def delete(self, user_id: str, key: str) -> None:
        """Deletes authorization data for a given user and key."""
        pass
