import asyncio
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

from sk_agents.exceptions import (
    PersistenceCreateError,
    PersistenceDeleteError,
    PersistenceLoadError,
    PersistenceUpdateError,
)
from sk_agents.persistence.in_memory_persistence_manager import InMemoryPersistenceManager
from sk_agents.ska_types import ContentType, MultiModalItem
from sk_agents.tealagents.models import AgentTask, AgentTaskItem


@pytest.fixture
def persistence_manager():
    """Provides a fresh InMemoryPersistenceManager for each test."""
    yield InMemoryPersistenceManager()


@pytest.fixture
def task_item():
    agent_task_item = AgentTaskItem(
        task_id="task-id-1",
        role="user",
        item=MultiModalItem(content_type=ContentType.TEXT, content="test"),
        request_id="request_id_test",
        updated=datetime.now(),
        pending_tool_calls=None,
    )
    return agent_task_item


@pytest.fixture
def task_a():
    """Provides a sample AgentTask for testing."""
    agent_task_item = AgentTaskItem(
        task_id="task-id-1",
        role="user",
        item=MultiModalItem(content_type=ContentType.TEXT, content="text-a"),
        request_id="request_id_a",
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


@pytest.fixture
def task_b():
    """Provides another sample AgentTask for testing."""
    agent_task_item = AgentTaskItem(
        task_id="task-id-2",
        role="user",
        item=MultiModalItem(content_type=ContentType.TEXT, content="text-b"),
        request_id="request_id_b",
        updated=datetime.now(),
        pending_tool_calls=None,
    )

    return AgentTask(
        task_id="task-id-2",
        session_id="session_id_2",
        user_id="test_user_id",
        items=[agent_task_item],
        created_at=datetime.now(),
        last_updated=datetime.now(),
        status="Running",
    )


@pytest.fixture
def task_with_duplicate_request_ids():
    """Create a task with multiple items having the same request_id"""
    now = datetime.now()
    request_id = "duplicate-request-123"

    items = [
        AgentTaskItem(
            task_id="task-duplicate",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="User message 1"),
            request_id=request_id,  # Same request_id
            updated=now,
            pending_tool_calls=None,
        ),
        AgentTaskItem(
            task_id="task-duplicate",
            role="assistant",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Assistant response"),
            request_id=request_id,  # Same request_id
            updated=now,
            pending_tool_calls=None,
        ),
        AgentTaskItem(
            task_id="task-duplicate",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="User message 2"),
            request_id=request_id,  # Same request_id again
            updated=now,
            pending_tool_calls=None,
        ),
    ]

    return AgentTask(
        task_id="task-duplicate",
        session_id="session-duplicate",
        user_id="user-duplicate",
        items=items,
        created_at=now,
        last_updated=now,
        status="Running",
    )


@pytest.fixture
def task_with_mixed_request_ids():
    """Create a task with items having different request_ids"""
    now = datetime.now()

    items = [
        AgentTaskItem(
            task_id="task-mixed",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Message A"),
            request_id="request-A",
            updated=now,
            pending_tool_calls=None,
        ),
        AgentTaskItem(
            task_id="task-mixed",
            role="assistant",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Response B"),
            request_id="request-B",
            updated=now,
            pending_tool_calls=None,
        ),
        AgentTaskItem(
            task_id="task-mixed",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Message A2"),
            request_id="request-A",  # Duplicate of first item's request_id
            updated=now,
            pending_tool_calls=None,
        ),
    ]

    return AgentTask(
        task_id="task-mixed",
        session_id="session-mixed",
        user_id="user-mixed",
        items=items,
        created_at=now,
        last_updated=now,
        status="Running",
    )


@pytest.mark.asyncio
async def test_create_and_load_task(persistence_manager, task_a):
    """Test creating a task and then loading it successfully."""
    await persistence_manager.create(task_a)
    loaded_task = await persistence_manager.load(task_a.task_id)
    assert loaded_task == task_a


@pytest.mark.asyncio
async def test_load_non_existent_task(persistence_manager):
    """Test loading a task that does not exist should return None."""
    loaded_task = await persistence_manager.load("non_existent_id")
    assert loaded_task is None


@pytest.mark.asyncio
async def test_load_unexpected_error_handling(persistence_manager):
    """Test that unexpected errors in load method are wrapped in PersistenceLoadError"""
    mock_memory = MagicMock()
    mock_memory.get.side_effect = RuntimeError("Simulated runtime error")

    with patch.object(persistence_manager, "in_memory", mock_memory):
        with pytest.raises(PersistenceLoadError):
            await persistence_manager.load("test-task")


@pytest.mark.asyncio
async def test_create_duplicate_task(persistence_manager, task_a):
    """Test creating a task with an ID that already exists should raise PersistenceCreateError."""
    await persistence_manager.create(task_a)
    with pytest.raises(PersistenceCreateError):
        await persistence_manager.create(task_a)


@pytest.mark.asyncio
async def test_update_existing_task(persistence_manager, task_a):
    """Test updating an existing task successfully."""
    await persistence_manager.create(task_a)
    task_a.status = "Paused"
    task_a.last_updated = datetime.now()
    await persistence_manager.update(task_a)
    loaded_task = await persistence_manager.load(task_a.task_id)
    assert loaded_task == task_a


@pytest.mark.asyncio
async def test_update_non_existent_task(persistence_manager, task_b):
    """Test updating a task that does not exist should raise ValueError."""
    with pytest.raises(PersistenceUpdateError):
        await persistence_manager.update(task_b)


@pytest.mark.asyncio
async def test_delete_existing_task(persistence_manager, task_a):
    """Test deleting an existing task successfully."""
    await persistence_manager.create(task_a)
    await persistence_manager.delete(task_a.task_id)
    loaded_task = await persistence_manager.load(task_a.task_id)
    assert loaded_task is None


@pytest.mark.asyncio
async def test_delete_non_existent_task(persistence_manager):
    """Test deleting a task that does not exist should raise ValueError."""
    with pytest.raises(PersistenceDeleteError):
        await persistence_manager.delete("non_existent_id")


@pytest.mark.asyncio
async def test_delete_unexpected_error_handling(persistence_manager, task_a):
    """Test that unexpected errors in delete method are wrapped in PersistenceDeleteError"""
    await persistence_manager.create(task_a)

    class FailingSet(set):
        def discard(self, elem):
            raise RuntimeError("Simulated index error")

    original_set = persistence_manager.item_request_id_index["request_id_a"]
    persistence_manager.item_request_id_index["request_id_a"] = FailingSet(original_set)

    with pytest.raises(PersistenceDeleteError):
        await persistence_manager.delete("task-id-1")


@pytest.mark.asyncio
async def test_concurrent_create(persistence_manager, task_item):
    """Test that concurrent create operations are handled correctly by the lock."""

    tasks_to_create = [
        AgentTask(
            task_id=f"task-id-{_}",
            session_id="concurrent_session_id_",
            user_id="test_user_id",
            items=[task_item],
            created_at=datetime.now(),
            last_updated=datetime.now(),
            status="Running",
        )
        for _ in range(100)
    ]

    async def create_task_wrapper(task):
        await persistence_manager.create(task)

    await asyncio.gather(*[create_task_wrapper(task) for task in tasks_to_create])

    # Verify all tasks were created and no duplicates (by ID)
    assert len(persistence_manager.in_memory) == len(tasks_to_create)
    for task in tasks_to_create:
        loaded_task = await persistence_manager.load(task.task_id)
        assert loaded_task == task


@pytest.mark.asyncio
async def test_concurrent_update(persistence_manager, task_item):
    """Test that concurrent update operations are handled correctly by the lock."""
    original_tasks = [
        AgentTask(
            task_id=f"task-id-{_}",
            session_id="concurrent_session_id_",
            user_id="test_user_id",
            items=[task_item],
            created_at=datetime.now(),
            last_updated=datetime.now(),
            status="Running",
        )
        for _ in range(50)
    ]
    for task in original_tasks:
        await persistence_manager.create(task)

    async def update_task_wrapper(task):
        task.status = "Paused"
        task.last_updated = datetime.now()
        await persistence_manager.update(task)

    await asyncio.gather(*[update_task_wrapper(task) for task in original_tasks])

    # Verify all tasks were updated to their final state
    for task in original_tasks:
        loaded_task = await persistence_manager.load(task.task_id)
        assert loaded_task.status == "Paused"


@pytest.mark.asyncio
async def test_concurrent_mixed_operations(persistence_manager, task_item):
    """Test mixed concurrent operations (create, update, delete, load)."""
    initial_tasks = [
        AgentTask(
            task_id=f"task-id-{_}",
            session_id="concurrent_session_id_",
            user_id="test_user_id",
            items=[task_item],
            created_at=datetime.now(),
            last_updated=datetime.now(),
            status="Running",
        )
        for _ in range(20)
    ]
    for task in initial_tasks:
        await persistence_manager.create(task)

    tasks_to_delete = initial_tasks[0:5]
    tasks_to_update = initial_tasks[5:10]
    tasks_to_load = initial_tasks[10:15]
    tasks_to_create_new = [
        AgentTask(
            task_id=f"task-id-{_}",
            session_id="concurrent_session_id_",
            user_id="test_user_id",
            items=[task_item],
            created_at=datetime.now(),
            last_updated=datetime.now(),
            status="Running",
        )
        for _ in range(20, 25)
    ]

    async def run_operations():
        # Create new
        create_coros = [persistence_manager.create(t) for t in tasks_to_create_new]

        # Update existing
        async def update_task_workflow(task):
            task.status = "Completed"
            task.last_updated = datetime.now()
            await persistence_manager.update(task)

        update_coros = [update_task_workflow(t) for t in tasks_to_update]

        # Delete existing
        delete_coros = [persistence_manager.delete(t.task_id) for t in tasks_to_delete]
        # Load existing
        load_coros = [persistence_manager.load(t.task_id) for t in tasks_to_load]

        await asyncio.gather(
            *create_coros,
            *update_coros,
            *delete_coros,
            *load_coros,
            return_exceptions=True,  # Allow other tasks to run if one fails
        )

    await run_operations()

    # Verify state after concurrent operations
    for task in tasks_to_create_new:
        loaded = await persistence_manager.load(task.task_id)
        assert loaded.task_id == task.task_id
    for task in tasks_to_update:
        loaded = await persistence_manager.load(task.task_id)
        assert loaded.status == "Completed"
    for task in tasks_to_delete:
        loaded = await persistence_manager.load(task.task_id)
        assert loaded is None
    for task in tasks_to_load:
        assert await persistence_manager.load(task.task_id) is not None


@pytest.mark.asyncio
async def test_create_task_with_duplicate_request_ids(
    persistence_manager, task_with_duplicate_request_ids
):
    """Test creating a task where multiple items have the same request_id"""
    await persistence_manager.create(task_with_duplicate_request_ids)

    # Verify task is stored
    loaded_task = await persistence_manager.load("task-duplicate")
    assert loaded_task is not None
    assert loaded_task.task_id == "task-duplicate"
    assert len(loaded_task.items) == 3

    # Verify all items have the same request_id
    for item in loaded_task.items:
        assert item.request_id == "duplicate-request-123"

    # Verify index contains the task for this request_id
    assert "duplicate-request-123" in persistence_manager.item_request_id_index
    assert "task-duplicate" in persistence_manager.item_request_id_index["duplicate-request-123"]


@pytest.mark.asyncio
async def test_load_by_request_id_with_duplicates(
    persistence_manager, task_with_duplicate_request_ids
):
    """Test loading by request_id when a task has multiple items with same request_id"""
    await persistence_manager.create(task_with_duplicate_request_ids)

    # Load by the shared request_id
    found_task = await persistence_manager.load_by_request_id("duplicate-request-123")

    assert found_task is not None
    assert found_task.task_id == "task-duplicate"
    assert len(found_task.items) == 3

    # Verify all items still have the same request_id
    for item in found_task.items:
        assert item.request_id == "duplicate-request-123"


@pytest.mark.asyncio
async def test_index_efficiency_with_duplicates(
    persistence_manager, task_with_duplicate_request_ids
):
    """Test that index doesn't create duplicate entries for same request_id in same task"""
    await persistence_manager.create(task_with_duplicate_request_ids)

    # Check that the index only has one entry for the task, even though
    # multiple items have the same request_id
    request_id_set = persistence_manager.item_request_id_index["duplicate-request-123"]
    assert len(request_id_set) == 1
    assert "task-duplicate" in request_id_set


@pytest.mark.asyncio
async def test_update_task_with_duplicate_request_ids(
    persistence_manager, task_with_duplicate_request_ids
):
    """Test updating a task that has items with duplicate request_ids"""
    await persistence_manager.create(task_with_duplicate_request_ids)

    # Update the task by adding another item with the same request_id
    now = datetime.now()
    new_item = AgentTaskItem(
        task_id="task-duplicate",
        role="assistant",
        item=MultiModalItem(content_type=ContentType.TEXT, content="Another assistant response"),
        request_id="duplicate-request-123",  # Same request_id again
        updated=now,
        pending_tool_calls=None,
    )

    updated_task = AgentTask(
        task_id="task-duplicate",
        session_id="session-duplicate",
        user_id="user-duplicate",
        items=task_with_duplicate_request_ids.items + [new_item],
        created_at=task_with_duplicate_request_ids.created_at,
        last_updated=now,
        status="Running",
    )

    await persistence_manager.update(updated_task)

    # Verify the task was updated
    loaded_task = await persistence_manager.load("task-duplicate")
    assert len(loaded_task.items) == 4

    # Verify index still only has one entry for the task
    request_id_set = persistence_manager.item_request_id_index["duplicate-request-123"]
    assert len(request_id_set) == 1
    assert "task-duplicate" in request_id_set


@pytest.mark.asyncio
async def test_update_changing_duplicate_request_ids(
    persistence_manager, task_with_duplicate_request_ids
):
    """Test updating a task to change some of the duplicate request_ids"""
    await persistence_manager.create(task_with_duplicate_request_ids)

    # Change some items to have different request_ids
    now = datetime.now()
    updated_items = [
        AgentTaskItem(
            task_id="task-duplicate",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Changed message 1"),
            request_id="new-request-456",  # Changed
            updated=now,
            pending_tool_calls=None,
        ),
        AgentTaskItem(
            task_id="task-duplicate",
            role="assistant",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Kept response"),
            request_id="duplicate-request-123",  # Kept same
            updated=now,
            pending_tool_calls=None,
        ),
        AgentTaskItem(
            task_id="task-duplicate",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Changed message 2"),
            request_id="another-request-789",  # Changed
            updated=now,
            pending_tool_calls=None,
        ),
    ]

    updated_task = AgentTask(
        task_id="task-duplicate",
        session_id="session-duplicate",
        user_id="user-duplicate",
        items=updated_items,
        created_at=task_with_duplicate_request_ids.created_at,
        last_updated=now,
        status="Running",
    )

    await persistence_manager.update(updated_task)

    # Verify index is updated correctly
    # Should have task-duplicate in three different request_id sets
    assert "task-duplicate" in persistence_manager.item_request_id_index["new-request-456"]
    assert "task-duplicate" in persistence_manager.item_request_id_index["duplicate-request-123"]
    assert "task-duplicate" in persistence_manager.item_request_id_index["another-request-789"]

    # Each should contain only task-duplicate
    assert len(persistence_manager.item_request_id_index["new-request-456"]) == 1
    assert len(persistence_manager.item_request_id_index["duplicate-request-123"]) == 1
    assert len(persistence_manager.item_request_id_index["another-request-789"]) == 1


@pytest.mark.asyncio
async def test_delete_task_with_duplicate_request_ids(
    persistence_manager, task_with_duplicate_request_ids
):
    """Test deleting a task that has items with duplicate request_ids"""
    await persistence_manager.create(task_with_duplicate_request_ids)

    # Verify task exists and index is populated
    assert "duplicate-request-123" in persistence_manager.item_request_id_index
    assert "task-duplicate" in persistence_manager.item_request_id_index["duplicate-request-123"]

    # Delete the task
    await persistence_manager.delete("task-duplicate")

    # Verify task is removed from storage
    loaded_task = await persistence_manager.load("task-duplicate")
    assert loaded_task is None

    # Verify index is cleaned up completely
    assert "duplicate-request-123" not in persistence_manager.item_request_id_index


@pytest.mark.asyncio
async def test_mixed_request_ids_scenario(persistence_manager, task_with_mixed_request_ids):
    """Test a task with items having both duplicate and unique request_ids"""
    await persistence_manager.create(task_with_mixed_request_ids)

    # Verify index contains entries for both request_ids
    assert "request-A" in persistence_manager.item_request_id_index
    assert "request-B" in persistence_manager.item_request_id_index
    assert "task-mixed" in persistence_manager.item_request_id_index["request-A"]
    assert "task-mixed" in persistence_manager.item_request_id_index["request-B"]

    # Test loading by each request_id returns the same task
    task_a = await persistence_manager.load_by_request_id("request-A")
    task_b = await persistence_manager.load_by_request_id("request-B")

    assert task_a is not None
    assert task_b is not None
    assert task_a.task_id == task_b.task_id == "task-mixed"


@pytest.mark.asyncio
async def test_multiple_tasks_same_request_id_priority(persistence_manager):
    """Test when multiple tasks contain items with the same request_id"""
    now = datetime.now()

    # Create two tasks with items having the same request_id
    task1_items = [
        AgentTaskItem(
            task_id="task-1",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Task 1 message"),
            request_id="shared-request-123",
            updated=now,
            pending_tool_calls=None,
        )
    ]

    task2_items = [
        AgentTaskItem(
            task_id="task-2",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Task 2 message"),
            request_id="shared-request-123",
            updated=now,
            pending_tool_calls=None,
        )
    ]

    task1 = AgentTask(
        task_id="task-1",
        session_id="session-1",
        user_id="user-1",
        items=task1_items,
        created_at=now,
        last_updated=now,
        status="Running",
    )

    task2 = AgentTask(
        task_id="task-2",
        session_id="session-2",
        user_id="user-2",
        items=task2_items,
        created_at=now,
        last_updated=now,
        status="Running",
    )

    await persistence_manager.create(task1)
    await persistence_manager.create(task2)

    # Verify index contains both tasks
    request_id_set = persistence_manager.item_request_id_index["shared-request-123"]
    assert len(request_id_set) == 2
    assert "task-1" in request_id_set
    assert "task-2" in request_id_set

    # When loading by request_id, should return one of the tasks
    found_task = await persistence_manager.load_by_request_id("shared-request-123")
    assert found_task is not None
    assert found_task.task_id in ["task-1", "task-2"]


@pytest.mark.asyncio
async def test_load_by_request_id_not_found(persistence_manager):
    """Test loading by request_id when no task contains that request_id"""
    result = await persistence_manager.load_by_request_id("nonexistent-request")
    assert result is None


@pytest.mark.asyncio
async def test_load_by_request_id_unexpected_error_handling(persistence_manager):
    """Test that unexpected errors in load_by_request_id
    method are wrapped in PersistenceLoadError"""
    mock_index = MagicMock()
    mock_index.get.side_effect = RuntimeError("Simulated runtime error")

    with patch.object(persistence_manager, "item_request_id_index", mock_index):
        with pytest.raises(PersistenceLoadError):
            await persistence_manager.load_by_request_id("test-request")


@pytest.mark.asyncio
async def test_concurrent_operations_with_duplicate_request_ids(persistence_manager):
    """Test concurrent operations on tasks with duplicate request_ids"""
    now = datetime.now()

    # Create multiple tasks, each with items having duplicate request_ids
    tasks_to_create = []
    for i in range(10):
        items = [
            AgentTaskItem(
                task_id=f"concurrent-task-{i}",
                role="user",
                item=MultiModalItem(content_type=ContentType.TEXT, content=f"Message {j}"),
                request_id=f"shared-request-{i % 3}",  # 3 different request_ids shared across tasks
                updated=now,
                pending_tool_calls=None,
            )
            for j in range(3)  # 3 items per task, all with same request_id
        ]

        task = AgentTask(
            task_id=f"concurrent-task-{i}",
            session_id=f"session-{i}",
            user_id=f"user-{i}",
            items=items,
            created_at=now,
            last_updated=now,
            status="Running",
        )
        tasks_to_create.append(task)

    # Create all tasks concurrently
    await asyncio.gather(*[persistence_manager.create(task) for task in tasks_to_create])

    # Verify index is correctly maintained
    for i in range(3):
        request_id = f"shared-request-{i}"
        request_id_set = persistence_manager.item_request_id_index[request_id]

        # Should contain tasks where i % 3 == current i
        expected_tasks = {f"concurrent-task-{j}" for j in range(10) if j % 3 == i}
        assert request_id_set == expected_tasks

    # Test concurrent load_by_request_id operations
    load_results = await asyncio.gather(
        *[persistence_manager.load_by_request_id(f"shared-request-{i % 3}") for i in range(20)]
    )

    # All loads should succeed and return valid tasks
    for result in load_results:
        assert result is not None
        assert result.task_id.startswith("concurrent-task-")
