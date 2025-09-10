import threading

from sk_agents.auth_storage.models import AuthData
from sk_agents.auth_storage.secure_auth_storage_manager import SecureAuthStorageManager


class InMemorySecureAuthStorageManager(SecureAuthStorageManager):
    """A thread-safe, in-memory implementation of the SecureAuthStorageManager."""

    def __init__(self):
        self._storage: dict[str, dict[str, AuthData]] = {}
        self._lock = threading.Lock()

    def store(self, user_id: str, key: str, data: AuthData) -> None:
        with self._lock:
            if user_id not in self._storage:
                self._storage[user_id] = {}
            self._storage[user_id][key] = data

    def retrieve(self, user_id: str, key: str) -> AuthData | None:
        with self._lock:
            return self._storage.get(user_id, {}).get(key)

    def delete(self, user_id: str, key: str) -> None:
        with self._lock:
            if user_id in self._storage and key in self._storage[user_id]:
                del self._storage[user_id][key]
