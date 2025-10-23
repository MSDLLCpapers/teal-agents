from datetime import datetime, timedelta

import pytest

from sk_agents.auth_storage.models import OAuth2AuthData
from sk_agents.auth_storage.secure_auth_storage_manager import SecureAuthStorageManager


@pytest.fixture
def sample_auth_data():
    """Provides a sample OAuth2AuthData instance."""
    return OAuth2AuthData(
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        expires_at=datetime.now() + timedelta(hours=1),
        scopes=["read", "write"],
    )


def test_cannot_instantiate_abstract_class():
    """Test that SecureAuthStorageManager cannot be instantiated directly."""
    with pytest.raises(TypeError) as exc_info:
        SecureAuthStorageManager()

    # Verify the error message indicates abstract methods
    assert "abstract" in str(exc_info.value).lower()


def test_subclass_without_implementations_fails():
    """Test that a subclass without implementing abstract methods cannot be instantiated."""

    class IncompleteManager(SecureAuthStorageManager):
        pass

    with pytest.raises(TypeError) as exc_info:
        IncompleteManager()

    assert "abstract" in str(exc_info.value).lower()


def test_subclass_with_partial_implementations_fails():
    """Test that a subclass with only some abstract methods implemented fails."""

    class PartialManager(SecureAuthStorageManager):
        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            pass

    with pytest.raises(TypeError) as exc_info:
        PartialManager()

    assert "abstract" in str(exc_info.value).lower()


def test_subclass_missing_store():
    """Test that a subclass missing only store method fails."""

    class MissingStore(SecureAuthStorageManager):
        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            pass

        def delete(self, user_id: str, key: str) -> None:
            pass

    with pytest.raises(TypeError):
        MissingStore()


def test_subclass_missing_retrieve():
    """Test that a subclass missing only retrieve method fails."""

    class MissingRetrieve(SecureAuthStorageManager):
        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            pass

        def delete(self, user_id: str, key: str) -> None:
            pass

    with pytest.raises(TypeError):
        MissingRetrieve()


def test_subclass_missing_delete():
    """Test that a subclass missing only delete method fails."""

    class MissingDelete(SecureAuthStorageManager):
        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            pass

        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            pass

    with pytest.raises(TypeError):
        MissingDelete()


def test_concrete_implementation_works(sample_auth_data):
    """Test that a complete concrete implementation can be instantiated and used."""

    class ConcreteManager(SecureAuthStorageManager):
        def __init__(self):
            self.storage = {}

        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            if user_id not in self.storage:
                self.storage[user_id] = {}
            self.storage[user_id][key] = data

        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            if user_id in self.storage:
                return self.storage[user_id].get(key)
            return None

        def delete(self, user_id: str, key: str) -> None:
            if user_id in self.storage and key in self.storage[user_id]:
                del self.storage[user_id][key]

    # Should instantiate successfully
    manager = ConcreteManager()

    # Test all methods work
    manager.store("user1", "key1", sample_auth_data)
    retrieved = manager.retrieve("user1", "key1")
    assert retrieved == sample_auth_data
    assert retrieved.access_token == "test_access_token"

    manager.delete("user1", "key1")
    deleted = manager.retrieve("user1", "key1")
    assert deleted is None


def test_abstract_methods_signature_verification():
    """Test that abstract methods have correct signatures."""

    class TestManager(SecureAuthStorageManager):
        # Implement with explicit signatures to verify type hints
        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            """Must accept user_id, key, and AuthData; return None"""
            pass

        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            """Must accept user_id and key; return AuthData or None"""
            pass

        def delete(self, user_id: str, key: str) -> None:
            """Must accept user_id and key; return None"""
            pass

    # Should instantiate successfully with correct signatures
    manager = TestManager()
    assert manager is not None


def test_inheritance_chain():
    """Test that SecureAuthStorageManager properly inherits from ABC."""
    from abc import ABC

    assert issubclass(SecureAuthStorageManager, ABC)


def test_all_methods_are_abstract():
    """Test that all expected methods are marked as abstract."""
    abstract_methods = SecureAuthStorageManager.__abstractmethods__

    expected_methods = {"store", "retrieve", "delete"}
    assert abstract_methods == expected_methods


def test_multiple_subclasses_independent():
    """Test that multiple subclasses can coexist independently."""

    class ManagerA(SecureAuthStorageManager):
        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            pass

        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            pass

        def delete(self, user_id: str, key: str) -> None:
            pass

    class ManagerB(SecureAuthStorageManager):
        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            pass

        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            pass

        def delete(self, user_id: str, key: str) -> None:
            pass

    # Both should instantiate independently
    manager_a = ManagerA()
    manager_b = ManagerB()

    assert manager_a is not manager_b
    assert not isinstance(manager_a, type(manager_b))
    assert isinstance(manager_a, SecureAuthStorageManager)
    assert isinstance(manager_b, SecureAuthStorageManager)


def test_pass_through_implementations(sample_auth_data):
    """Test implementations that delegate to parent's pass statements."""

    class PassThroughManager(SecureAuthStorageManager):
        """Manager that calls super() to execute parent pass statements."""

        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            # This will execute the pass in the abstract method
            super().store(user_id, key, data)

        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            # This will execute the pass in the abstract method
            return super().retrieve(user_id, key)

        def delete(self, user_id: str, key: str) -> None:
            # This will execute the pass in the abstract method
            super().delete(user_id, key)

    manager = PassThroughManager()

    # Execute all methods through super() to hit the pass statements
    manager.store("user1", "key1", sample_auth_data)

    result = manager.retrieve("user1", "key1")
    assert result is None  # pass returns None implicitly

    manager.delete("user1", "key1")


def test_method_docstrings_exist():
    """Test that abstract methods have proper docstrings."""
    assert SecureAuthStorageManager.store.__doc__ is not None
    assert "Stores authorization data" in SecureAuthStorageManager.store.__doc__

    assert SecureAuthStorageManager.retrieve.__doc__ is not None
    assert "Retrieves authorization data" in SecureAuthStorageManager.retrieve.__doc__

    assert SecureAuthStorageManager.delete.__doc__ is not None
    assert "Deletes authorization data" in SecureAuthStorageManager.delete.__doc__


def test_concrete_implementation_with_multiple_users(sample_auth_data):
    """Test concrete implementation with multiple users and keys."""

    class ConcreteManager(SecureAuthStorageManager):
        def __init__(self):
            self.storage = {}

        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            if user_id not in self.storage:
                self.storage[user_id] = {}
            self.storage[user_id][key] = data

        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            if user_id in self.storage:
                return self.storage[user_id].get(key)
            return None

        def delete(self, user_id: str, key: str) -> None:
            if user_id in self.storage and key in self.storage[user_id]:
                del self.storage[user_id][key]

    manager = ConcreteManager()

    # Store data for multiple users
    auth_data_1 = OAuth2AuthData(
        access_token="token1",
        expires_at=datetime.now() + timedelta(hours=1),
        scopes=["read"],
    )
    auth_data_2 = OAuth2AuthData(
        access_token="token2",
        expires_at=datetime.now() + timedelta(hours=2),
        scopes=["write"],
    )

    manager.store("user1", "key1", auth_data_1)
    manager.store("user2", "key1", auth_data_2)
    manager.store("user1", "key2", sample_auth_data)

    # Verify retrieval
    assert manager.retrieve("user1", "key1").access_token == "token1"
    assert manager.retrieve("user2", "key1").access_token == "token2"
    assert manager.retrieve("user1", "key2").access_token == "test_access_token"

    # Verify isolation between users
    manager.delete("user1", "key1")
    assert manager.retrieve("user1", "key1") is None
    assert manager.retrieve("user2", "key1") is not None  # Should still exist


def test_method_parameters_validation():
    """Test that methods accept correct parameter types."""

    class ValidatingManager(SecureAuthStorageManager):
        def store(self, user_id: str, key: str, data: OAuth2AuthData) -> None:
            assert isinstance(user_id, str)
            assert isinstance(key, str)
            assert isinstance(data, OAuth2AuthData)

        def retrieve(self, user_id: str, key: str) -> OAuth2AuthData | None:
            assert isinstance(user_id, str)
            assert isinstance(key, str)
            return None

        def delete(self, user_id: str, key: str) -> None:
            assert isinstance(user_id, str)
            assert isinstance(key, str)

    manager = ValidatingManager()

    auth_data = OAuth2AuthData(
        access_token="token",
        expires_at=datetime.now() + timedelta(hours=1),
        scopes=[],
    )

    # These should all pass without assertion errors
    manager.store("user", "key", auth_data)
    manager.retrieve("user", "key")
    manager.delete("user", "key")
