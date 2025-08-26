import threading
import pytest
from datetime import datetime, timedelta
from src.sk_agents.auth_storage.in_memory_secure_auth_storage_manager import InMemorySecureAuthStorageManager
from src.sk_agents.auth_storage.models import OAuth2AuthData

@pytest.fixture
def auth_manager():
    """Provides a fresh instance of the storage manager for each test."""
    return InMemorySecureAuthStorageManager()

@pytest.fixture
def sample_auth_data():
    """Provides a sample OAuth2AuthData instance."""
    return OAuth2AuthData(
        access_token="test_access_token",
        expires_at=datetime.now() + timedelta(hours=1),
        scopes=["read", "write"]
    )

def test_store_and_retrieve(auth_manager, sample_auth_data):
    """Test that data can be stored and retrieved successfully."""
    user_id = "user123"
    key = "tool_a"
    auth_manager.store(user_id, key, sample_auth_data)
    retrieved_data = auth_manager.retrieve(user_id, key)
    assert retrieved_data is not None
    assert retrieved_data.access_token == sample_auth_data.access_token

def test_retrieve_non_existent_key(auth_manager):
    """Test retrieving a key that doesn't exist returns None."""
    retrieved_data = auth_manager.retrieve("non_existent_user", "non_existent_key")
    assert retrieved_data is None

def test_delete(auth_manager, sample_auth_data):
    """Test that a stored item can be deleted successfully."""
    user_id = "user123"
    key = "tool_b"
    auth_manager.store(user_id, key, sample_auth_data)
    assert auth_manager.retrieve(user_id, key) is not None
    auth_manager.delete(user_id, key)
    assert auth_manager.retrieve(user_id, key) is None

def test_delete_non_existent_key(auth_manager):
    """Test that deleting a non-existent key doesn't raise an error."""
    auth_manager.delete("user_x", "key_y")
    assert True  # The test passes if no exception is raised

def test_concurrency(auth_manager):
    """Test that concurrent store and retrieve operations are thread-safe."""
    num_threads = 50
    num_operations_per_thread = 100
    user_id = "concurrent_user"
    threads = []
    
    def worker(thread_id):
        # Create a unique key and data for each thread
        key = f"tool_{thread_id}"
        data = OAuth2AuthData(
            access_token=f"token_{thread_id}",
            expires_at=datetime.now() + timedelta(hours=1),
            scopes=["read"]
        )
        
        # Perform mixed read/write operations
        for _ in range(num_operations_per_thread):
            # Store the data
            auth_manager.store(user_id, key, data)
            
            # Retrieve the data and check its integrity
            retrieved_data = auth_manager.retrieve(user_id, key)
            assert retrieved_data is not None
            assert retrieved_data.access_token == data.access_token
    
    # Start all worker threads
    for i in range(num_threads):
        thread = threading.Thread(target=worker, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join()
    
    # Final check: retrieve all items and verify their integrity
    for i in range(num_threads):
        key = f"tool_{i}"
        retrieved_data = auth_manager.retrieve(user_id, key)
        assert retrieved_data is not None
        assert retrieved_data.access_token == f"token_{i}"