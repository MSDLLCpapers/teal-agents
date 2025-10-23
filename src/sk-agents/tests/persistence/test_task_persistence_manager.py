from datetime import datetime
from unittest.mock import AsyncMock

import pytest

from sk_agents.persistence.task_persistence_manager import TaskPersistenceManager
from sk_agents.ska_types import ContentType, MultiModalItem
from sk_agents.tealagents.models import AgentTask, AgentTaskItem


@pytest.fixture
def sample_task():
    """Provides a sample AgentTask for testing."""
    agent_task_item = AgentTaskItem(
        task_id="task-id-1",
        role="user",
        item=MultiModalItem(content_type=ContentType.TEXT, content="test content"),
        request_id="request_id_test",
        updated=datetime.now(),
        pending_tool_calls=None,
    )

    return AgentTask(
        task_id="task-id-1",
        session_id="session_id_1",
        user_id="test_user_id",
        items=[agent_task_item],
        created_at=datetime.now(),
        last_updated=datetime.now(),
        status="Running",
    )


def test_cannot_instantiate_abstract_class():
    """Test that TaskPersistenceManager cannot be instantiated directly."""
    with pytest.raises(TypeError) as exc_info:
        TaskPersistenceManager()

    # Verify the error message indicates abstract methods
    assert "abstract" in str(exc_info.value).lower()


def test_subclass_without_implementations_fails():
    """Test that a subclass without implementing abstract methods cannot be instantiated."""

    class IncompleteManager(TaskPersistenceManager):
        pass

    with pytest.raises(TypeError) as exc_info:
        IncompleteManager()

    assert "abstract" in str(exc_info.value).lower()


def test_subclass_with_partial_implementations_fails():
    """Test that a subclass with only some abstract methods implemented fails."""

    class PartialManager(TaskPersistenceManager):
        async def create(self, task: AgentTask) -> None:
            pass

        async def load(self, task_id: str) -> AgentTask | None:
            pass

    with pytest.raises(TypeError) as exc_info:
        PartialManager()

    assert "abstract" in str(exc_info.value).lower()


def test_subclass_missing_create():
    """Test that a subclass missing only create method fails."""

    class MissingCreate(TaskPersistenceManager):
        async def load(self, task_id: str) -> AgentTask | None:
            pass

        async def update(self, task: AgentTask) -> None:
            pass

        async def delete(self, task_id: str) -> None:
            pass

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            pass

    with pytest.raises(TypeError):
        MissingCreate()


def test_subclass_missing_load():
    """Test that a subclass missing only load method fails."""

    class MissingLoad(TaskPersistenceManager):
        async def create(self, task: AgentTask) -> None:
            pass

        async def update(self, task: AgentTask) -> None:
            pass

        async def delete(self, task_id: str) -> None:
            pass

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            pass

    with pytest.raises(TypeError):
        MissingLoad()


def test_subclass_missing_update():
    """Test that a subclass missing only update method fails."""

    class MissingUpdate(TaskPersistenceManager):
        async def create(self, task: AgentTask) -> None:
            pass

        async def load(self, task_id: str) -> AgentTask | None:
            pass

        async def delete(self, task_id: str) -> None:
            pass

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            pass

    with pytest.raises(TypeError):
        MissingUpdate()


def test_subclass_missing_delete():
    """Test that a subclass missing only delete method fails."""

    class MissingDelete(TaskPersistenceManager):
        async def create(self, task: AgentTask) -> None:
            pass

        async def load(self, task_id: str) -> AgentTask | None:
            pass

        async def update(self, task: AgentTask) -> None:
            pass

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            pass

    with pytest.raises(TypeError):
        MissingDelete()


def test_subclass_missing_load_by_request_id():
    """Test that a subclass missing only load_by_request_id method fails."""

    class MissingLoadByRequestId(TaskPersistenceManager):
        async def create(self, task: AgentTask) -> None:
            pass

        async def load(self, task_id: str) -> AgentTask | None:
            pass

        async def update(self, task: AgentTask) -> None:
            pass

        async def delete(self, task_id: str) -> None:
            pass

    with pytest.raises(TypeError):
        MissingLoadByRequestId()


@pytest.mark.asyncio
async def test_concrete_implementation_works(sample_task):
    """Test that a complete concrete implementation can be instantiated and used."""

    class ConcreteManager(TaskPersistenceManager):
        def __init__(self):
            self.storage = {}

        async def create(self, task: AgentTask) -> None:
            self.storage[task.task_id] = task

        async def load(self, task_id: str) -> AgentTask | None:
            return self.storage.get(task_id)

        async def update(self, task: AgentTask) -> None:
            if task.task_id in self.storage:
                self.storage[task.task_id] = task

        async def delete(self, task_id: str) -> None:
            if task_id in self.storage:
                del self.storage[task_id]

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            for task in self.storage.values():
                for item in task.items:
                    if item.request_id == request_id:
                        return task
            return None

    # Should instantiate successfully
    manager = ConcreteManager()

    # Test all methods work
    await manager.create(sample_task)
    loaded = await manager.load(sample_task.task_id)
    assert loaded == sample_task

    sample_task.status = "Completed"
    await manager.update(sample_task)
    updated = await manager.load(sample_task.task_id)
    assert updated.status == "Completed"

    loaded_by_request = await manager.load_by_request_id("request_id_test")
    assert loaded_by_request == sample_task

    await manager.delete(sample_task.task_id)
    deleted = await manager.load(sample_task.task_id)
    assert deleted is None


def test_abstract_methods_signature_verification():
    """Test that abstract methods have correct signatures."""

    class TestManager(TaskPersistenceManager):
        # Implement with explicit signatures to verify type hints
        async def create(self, task: AgentTask) -> None:
            """Must accept AgentTask and return None"""
            pass

        async def load(self, task_id: str) -> AgentTask | None:
            """Must accept str and return AgentTask or None"""
            pass

        async def update(self, task: AgentTask) -> None:
            """Must accept AgentTask and return None"""
            pass

        async def delete(self, task_id: str) -> None:
            """Must accept str and return None"""
            pass

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            """Must accept str and return AgentTask or None"""
            pass

    # Should instantiate successfully with correct signatures
    manager = TestManager()
    assert manager is not None


def test_inheritance_chain():
    """Test that TaskPersistenceManager properly inherits from ABC."""
    from abc import ABC

    assert issubclass(TaskPersistenceManager, ABC)


def test_all_methods_are_abstract():
    """Test that all expected methods are marked as abstract."""
    abstract_methods = TaskPersistenceManager.__abstractmethods__

    expected_methods = {"create", "load", "update", "delete", "load_by_request_id"}
    assert abstract_methods == expected_methods


@pytest.mark.asyncio
async def test_concrete_implementation_with_mocks(sample_task):
    """Test concrete implementation using mocks to verify method calls."""

    class MockedManager(TaskPersistenceManager):
        def __init__(self):
            self.create_mock = AsyncMock()
            self.load_mock = AsyncMock()
            self.update_mock = AsyncMock()
            self.delete_mock = AsyncMock()
            self.load_by_request_id_mock = AsyncMock()

        async def create(self, task: AgentTask) -> None:
            await self.create_mock(task)

        async def load(self, task_id: str) -> AgentTask | None:
            return await self.load_mock(task_id)

        async def update(self, task: AgentTask) -> None:
            await self.update_mock(task)

        async def delete(self, task_id: str) -> None:
            await self.delete_mock(task_id)

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            return await self.load_by_request_id_mock(request_id)

    manager = MockedManager()

    # Test create is called
    await manager.create(sample_task)
    manager.create_mock.assert_called_once_with(sample_task)

    # Test load is called
    await manager.load("test-id")
    manager.load_mock.assert_called_once_with("test-id")

    # Test update is called
    await manager.update(sample_task)
    manager.update_mock.assert_called_once_with(sample_task)

    # Test delete is called
    await manager.delete("test-id")
    manager.delete_mock.assert_called_once_with("test-id")

    # Test load_by_request_id is called
    await manager.load_by_request_id("test-request")
    manager.load_by_request_id_mock.assert_called_once_with("test-request")


def test_multiple_subclasses_independent():
    """Test that multiple subclasses can coexist independently."""

    class ManagerA(TaskPersistenceManager):
        async def create(self, task: AgentTask) -> None:
            pass

        async def load(self, task_id: str) -> AgentTask | None:
            pass

        async def update(self, task: AgentTask) -> None:
            pass

        async def delete(self, task_id: str) -> None:
            pass

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            pass

    class ManagerB(TaskPersistenceManager):
        async def create(self, task: AgentTask) -> None:
            pass

        async def load(self, task_id: str) -> AgentTask | None:
            pass

        async def update(self, task: AgentTask) -> None:
            pass

        async def delete(self, task_id: str) -> None:
            pass

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            pass

    # Both should instantiate independently
    manager_a = ManagerA()
    manager_b = ManagerB()

    assert manager_a is not manager_b
    assert not isinstance(manager_a, type(manager_b))
    assert isinstance(manager_a, TaskPersistenceManager)
    assert isinstance(manager_b, TaskPersistenceManager)


@pytest.mark.asyncio
async def test_pass_through_implementations(sample_task):
    """Test implementations that delegate to parent's pass statements."""

    class PassThroughManager(TaskPersistenceManager):
        """Manager that calls super() to execute parent pass statements."""

        async def create(self, task: AgentTask) -> None:
            # This will execute the pass in the abstract method
            await super().create(task)

        async def load(self, task_id: str) -> AgentTask | None:
            # This will execute the pass in the abstract method
            return await super().load(task_id)

        async def update(self, task: AgentTask) -> None:
            # This will execute the pass in the abstract method
            await super().update(task)

        async def delete(self, task_id: str) -> None:
            # This will execute the pass in the abstract method
            await super().delete(task_id)

        async def load_by_request_id(self, request_id: str) -> AgentTask | None:
            # This will execute the pass in the abstract method
            return await super().load_by_request_id(request_id)

    manager = PassThroughManager()

    # Execute all methods through super() to hit the pass statements
    await manager.create(sample_task)
    result = await manager.load("test-id")
    assert result is None  # pass returns None implicitly

    await manager.update(sample_task)
    await manager.delete("test-id")

    result = await manager.load_by_request_id("test-request")
    assert result is None  # pass returns None implicitly
