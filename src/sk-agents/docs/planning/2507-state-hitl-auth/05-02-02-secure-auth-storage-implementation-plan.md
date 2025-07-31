# Phase 5 Implementation Plan: Secure Auth Storage Service

This document provides a detailed implementation plan for creating the Secure Auth Storage Service, as required by `05-02-01-secure-auth-storage.md`. This service will provide a flexible and abstract way to store and retrieve user-specific authorization credentials for tools.

The initial implementation will focus on an in-memory storage solution for OAuth 2.0 tokens, with a design that is extensible for future auth mechanisms and persistent storage backends.

## Task 1: Data Models for Authentication Data

**Objective:** Define the Pydantic models for storing different types of authentication credentials. This ensures a structured and validated approach to data handling.

- **Directory to Create:** `src/sk_agents/auth_storage/`
- **File to Create:** `src/sk_agents/auth_storage/models.py`
- **Details:**
    - Create a discriminated union of Pydantic models to represent various auth types.
    - The initial implementation will only include a model for OAuth 2.0.

```python
# src/sk_agents/auth_storage/models.py
from datetime import datetime
from typing import List, Literal, Union
from pydantic import BaseModel, Field

class BaseAuthData(BaseModel):
    """Base model for all authentication data types."""
    auth_type: str

class OAuth2AuthData(BaseAuthData):
    """Model for storing OAuth 2.0 credentials."""
    auth_type: Literal["oauth2"] = "oauth2"
    access_token: str
    refresh_token: str | None = None
    expires_at: datetime
    # The scopes this token is valid for.
    scopes: List[str]

# A union of all supported auth data types.
AuthData = Union[OAuth2AuthData]
```

## Task 2: Secure Auth Storage Abstraction

**Objective:** Define an abstract base class (`ABC`) that establishes the contract for all secure auth storage implementations.

- **File to Create:** `src/sk_agents/auth_storage/secure_auth_storage_manager.py`
- **Details:**
    - The ABC will define the core methods for storing, retrieving, and deleting user-specific auth data based on a key.
    - For OAuth 2.0, the `key` must be a composite key generated from the authorization server URL and the sorted list of required scopes (e.g., `f"{auth_server}|{sorted(scopes)}"`). This ensures that tokens are only reused when the exact set of permissions is required.

```python
# src/sk_agents/auth_storage/secure_auth_storage_manager.py
from abc import ABC, abstractmethod
from .models import AuthData

class SecureAuthStorageManager(ABC):
    """Abstract interface for storing and retrieving tool authorization information."""

    @abstractmethod
    def store(self, user_id: str, key: str, data: AuthData) -> None:
        """Stores authorization data for a given user and key."""
        ...

    @abstractmethod
    def retrieve(self, user_id: str, key: str) -> AuthData | None:
        """Retrieves authorization data for a given user and key."""
        ...

    @abstractmethod
    def delete(self, user_id: str, key: str) -> None:
        """Deletes authorization data for a given user and key."""
        ...
```

## Task 3: In-Memory Storage Implementation

**Objective:** Create a concrete, thread-safe, in-memory implementation of the `SecureAuthStorageManager`.

- **File to Create:** `src/sk_agents/auth_storage/in_memory_secure_auth_storage_manager.py`
- **Details:**
    - Implement the `InMemorySecureAuthStorageManager` class.
    - Use a nested dictionary (`dict[str, dict[str, AuthData]]`) for storage.
    - Employ `threading.Lock` to ensure all operations are thread-safe.

```python
# src/sk_agents/auth_storage/in_memory_secure_auth_storage_manager.py
import threading
from .models import AuthData
from .secure_auth_storage_manager import SecureAuthStorageManager

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
```

## Task 4: Singleton Factory Implementation

**Objective:** Develop a factory that provides a single, shared instance of the configured `SecureAuthStorageManager`.

- **File to Create:** `src/sk_agents/auth_storage/auth_storage_factory.py`
- **Details:**
    - The factory will dynamically import and instantiate the manager class based on environment variables.
    - It will follow the singleton pattern used by other factories in the project (e.g., `PersistenceFactory`).

## Task 5: Testing Strategy

**Objective:** Ensure the reliability, correctness, and thread safety of the new auth storage components.

- **File to Create:** `tests/test_secure_auth_storage.py`
- **Details:**
    1.  **Unit Tests:**
        - Verify that `OAuth2AuthData` model validation works as expected.
        - Test the `InMemorySecureAuthStorageManager` for correct `store`, `retrieve`, and `delete` behavior.
        - Write a multi-threaded test to confirm that concurrent read/write operations do not lead to race conditions or data corruption.
    2.  **Factory Tests:**
        - Test that the `AuthStorageFactory` correctly instantiates the `InMemorySecureAuthStorageManager` based on default environment variables.
        - Confirm that the factory always returns the same singleton instance.
        - Test error handling for invalid module or class names in environment variables.

## Task 6: Environment Variables and Configuration

**Objective:** Document the new environment variables required for configuring the Secure Auth Storage Service.

- **Details:** The application will use the following environment variables:
    - `TA_SECURE_AUTH_STORAGE_MANAGER_MODULE`: The Python module path for the storage manager implementation.
        - **Default:** `sk_agents.auth_storage.in_memory_secure_auth_storage_manager`
    - `TA_SECURE_AUTH_STORAGE_MANAGER_CLASS`: The class name of the storage manager implementation.
        - **Default:** `InMemorySecureAuthStorageManager`
