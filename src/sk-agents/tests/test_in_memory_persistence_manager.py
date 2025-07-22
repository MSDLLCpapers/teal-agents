import asyncio
from datetime import datetime

import pytest

from sk_agents.ska_types import ContentType, MultiModalItem
from sk_agents.tealagents.models import AgentTask, AgentTaskItem
from src.sk_agents.exceptions import (
    PersistenceCreateError,
    PersistenceDeleteError,
    PersistenceLoadError,
    PersistenceUpdateError,
)
from src.sk_agents.persistence.in_memory_persistence_manager import InMemoryPersistenceManager


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
        pending_tool_calls = None,
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
        pending_tool_calls = None,
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
        pending_tool_calls = None,
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


@pytest.mark.asyncio
async def test_create_and_load_task(persistence_manager, task_a):
    """Test creating a task and then loading it successfully."""
    await persistence_manager.create(task_a)
    loaded_task = await persistence_manager.load(task_a.task_id)
    assert loaded_task == task_a


@pytest.mark.asyncio
async def test_load_non_existent_task(persistence_manager):
    """Test loading a task that does not exist should raise ValueError."""
    with pytest.raises(PersistenceLoadError):
        await persistence_manager.load("non_existent_id")


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
    with pytest.raises(PersistenceLoadError):
        await persistence_manager.load(task_a.task_id)


@pytest.mark.asyncio
async def test_delete_non_existent_task(persistence_manager):
    """Test deleting a task that does not exist should raise ValueError."""
    with pytest.raises(PersistenceDeleteError):
        await persistence_manager.delete("non_existent_id")


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
        with pytest.raises(PersistenceLoadError):
            await persistence_manager.load(task.task_id)
    for task in tasks_to_load:
        assert await persistence_manager.load(task.task_id) is not None
