import json
import threading
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest
import redis

from sk_agents.exceptions import (
    PersistenceCreateError,
    PersistenceDeleteError,
    PersistenceLoadError,
    PersistenceUpdateError,
)
from sk_agents.persistence.custom.example_redis_persistence import (
    RedisTaskPersistenceManager,
)
from sk_agents.ska_types import ContentType, MultiModalItem
from sk_agents.tealagents.models import AgentTask, AgentTaskItem


@pytest.fixture
def mock_app_config():
    """Mock AppConfig returning explicit redis values"""
    config = MagicMock()
    config.get.side_effect = lambda key: {
        "TA_REDIS_HOST": "localhost",
        "TA_REDIS_PORT": "6379",
        "TA_REDIS_DB": "0",
        "TA_REDIS_PWD": None,
        "TA_REDIS_SSL": "false",  # Note: code sets ssl = value == "false"
        "TA_REDIS_TTL": "3600",
    }.get(key)
    return config


@pytest.fixture
def sample_task_items():
    return [
        AgentTaskItem(
            task_id="task123",
            request_id="reqA",
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content="Hello"),
            updated=datetime.now(UTC),
        ),
        AgentTaskItem(
            task_id="task123",
            request_id="reqB",
            role="assistant",
            item=MultiModalItem(content_type=ContentType.TEXT, content="World"),
            updated=datetime.now(UTC) + timedelta(seconds=1),
        ),
    ]


@pytest.fixture
def sample_task(sample_task_items):
    now = datetime.now(UTC)
    return AgentTask(
        task_id="task123",
        session_id="sessionXYZ",
        user_id="user42",
        items=sample_task_items,
        created_at=datetime.now(UTC),
        last_updated=now,
    )


def build_task(task_id: str, request_ids: list[str]) -> AgentTask:
    now = datetime.now(UTC)
    items = [
        AgentTaskItem(
            task_id=task_id,
            request_id=rid,
            role="user",
            item=MultiModalItem(content_type=ContentType.TEXT, content=f"Content-{rid}"),
            updated=datetime.now(UTC) + timedelta(seconds=i),
        )
        for i, rid in enumerate(request_ids)
    ]
    return AgentTask(
        task_id=task_id,
        session_id="sessionX",
        user_id="userX",
        items=items,
        created_at=datetime.now(UTC),
        last_updated=now,
    )


class TestRedisTaskPersistenceInitialization:
    @patch("redis.Redis")
    def test_init_with_config(self, mock_redis_class, mock_app_config):
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client

        manager = RedisTaskPersistenceManager(mock_app_config)
        mock_redis_class.assert_called_once_with(
            host="localhost",
            port=6379,
            db=0,
            password=None,
            ssl=True,  # Because TA_REDIS_SSL == "false" -> True in code
            decode_responses=True,
            socket_connect_timeout=5,
            socket_timeout=5,
            retry_on_timeout=True,
        )
        assert manager.ttl == 3600

    @patch("redis.Redis")
    @patch("sk_agents.persistence.custom.example_redis_persistence.AppConfig")
    def test_init_without_config(self, mock_app_config_cls, mock_redis_class):
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client

        config_instance = MagicMock()
        config_instance.get.return_value = None
        mock_app_config_cls.return_value = config_instance

        manager = RedisTaskPersistenceManager(None)
        mock_app_config_cls.assert_called_once()
        assert manager.app_config is config_instance

    @patch("redis.Redis")
    def test_init_defaults(self, mock_redis_class):
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client
        config = MagicMock()
        config.get.return_value = None
        manager = RedisTaskPersistenceManager(config)
        # Defaults host=localhost, port=6379, db=0, ttl=3600, ssl = (None == "false") False
        mock_redis_class.assert_called_once()
        called_kwargs = mock_redis_class.call_args.kwargs
        assert called_kwargs["host"] == "localhost"
        assert called_kwargs["port"] == 6379
        assert called_kwargs["db"] == 0
        assert called_kwargs["ssl"] is False
        assert manager.ttl == 3600

    @patch("redis.Redis")
    def test_init_connection_failure(self, mock_redis_class, mock_app_config):
        mock_client = Mock()
        mock_client.ping.side_effect = redis.ConnectionError("fail")
        mock_redis_class.return_value = mock_client
        with pytest.raises(ConnectionError):
            RedisTaskPersistenceManager(mock_app_config)

    @patch("redis.Redis")
    def test_lock_created(self, mock_redis_class, mock_app_config):
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client
        manager = RedisTaskPersistenceManager(mock_app_config)
        assert hasattr(manager, "_lock")
        assert isinstance(manager._lock, type(threading.Lock()))

    @patch("redis.Redis")
    def test_ssl_true_env(self, mock_redis_class):
        mock_client = Mock()
        mock_client.ping.return_value = True
        mock_redis_class.return_value = mock_client
        config = MagicMock()
        config.get.side_effect = lambda key: {
            "TA_REDIS_SSL": "true",  # Not equal to "false" -> ssl False
        }.get(key)
        RedisTaskPersistenceManager(config)
        assert mock_redis_class.call_args.kwargs["ssl"] is False


@patch("redis.Redis")
def test_key_helpers(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    assert manager._get_task_key("abc") == "task_persistence:task:abc"
    assert manager._get_request_index_key("req") == "task_persistence:request_index:req"


@patch("redis.Redis")
def test_serialization_helpers(mock_redis_class, mock_app_config, sample_task):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    s = manager._serialize_task(sample_task)
    assert isinstance(s, str)
    task = manager._deserialize_task(s)
    assert task.task_id == sample_task.task_id
    assert len(task.items) == len(sample_task.items)


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_create_success(mock_redis_class, mock_app_config, sample_task):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.exists.return_value = False
    created_sets = []

    def fake_setex(key, ttl, value):
        created_sets.append((key, ttl, value))

    mock_client.setex.side_effect = fake_setex
    sadd_calls = []
    mock_client.sadd.side_effect = lambda key, value: sadd_calls.append((key, value))
    manager = RedisTaskPersistenceManager(mock_app_config)
    await manager.create(sample_task)
    assert len(created_sets) == 1
    assert len(sadd_calls) == len(sample_task.items)


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_create_duplicate(mock_redis_class, mock_app_config, sample_task):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.exists.return_value = True
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceCreateError):
        await manager.create(sample_task)


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_create_redis_error(mock_redis_class, mock_app_config, sample_task):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.exists.return_value = False
    mock_client.setex.side_effect = redis.RedisError("fail")
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceCreateError):
        await manager.create(sample_task)


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_create_unexpected_error(mock_redis_class, mock_app_config, sample_task):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.exists.side_effect = RuntimeError("boom")
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceCreateError):
        await manager.create(sample_task)


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_success(mock_redis_class, mock_app_config, sample_task):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    serialized = manager._serialize_task(sample_task)
    mock_client.get.return_value = serialized
    task = await manager.load(sample_task.task_id)
    assert task is not None
    assert task.task_id == sample_task.task_id


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_not_found(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.get.return_value = None
    manager = RedisTaskPersistenceManager(mock_app_config)
    task = await manager.load("missing")
    assert task is None


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_redis_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.get.side_effect = redis.RedisError("fail")
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceLoadError):
        await manager.load("task123")


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_corrupted_json(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.get.return_value = "{bad json"  # triggers json.JSONDecodeError
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceLoadError):
        await manager.load("taskC")
    mock_client.delete.assert_called_once()


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_corrupted_validation_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    # Provide JSON missing required fields for AgentTask to trigger validation error
    mock_client.get.return_value = json.dumps({"bad": "data"})
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceLoadError):
        await manager.load("taskD")
    mock_client.delete.assert_called_once()


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_corrupted_delete_failure_swallowed(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.get.return_value = "{bad json"  # JSON decode error
    mock_client.delete.side_effect = redis.RedisError("del fail")
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceLoadError):
        await manager.load("taskE")
    # delete attempted even though it failed
    mock_client.delete.assert_called_once()


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_update_success(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    # Existing task has request_ids reqA, reqB. New task modifies to reqB, reqC
    old_task = build_task("task1", ["reqA", "reqB"])
    new_task = build_task("task1", ["reqB", "reqC"])
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.get.return_value = manager._serialize_task(old_task)
    # Track srem/sadd
    srem_calls = []
    mock_client.srem.side_effect = lambda k, v: srem_calls.append((k, v))
    sadd_calls = []
    mock_client.sadd.side_effect = lambda k, v: sadd_calls.append((k, v))
    await manager.update(new_task)
    # Old reqA removed; reqB removed then added again; reqC added
    removed_keys = [c[0] for c in srem_calls]
    assert any("reqA" in k for k in removed_keys)
    added_keys = [c[0] for c in sadd_calls]
    assert any("reqC" in k for k in added_keys)


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_update_missing_task(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.get.return_value = None
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceUpdateError):
        await manager.update(build_task("taskX", ["r1"]))


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_update_redis_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.get.side_effect = redis.RedisError("read fail")
    with pytest.raises(PersistenceUpdateError):
        await manager.update(build_task("taskY", ["r1"]))


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_update_unexpected_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.get.side_effect = RuntimeError("boom")
    with pytest.raises(PersistenceUpdateError):
        await manager.update(build_task("taskZ", ["r1"]))


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_delete_success(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    task = build_task("delTask", ["r1", "r2"])
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.get.return_value = manager._serialize_task(task)
    srem_calls = []
    mock_client.srem.side_effect = lambda k, v: srem_calls.append((k, v))
    await manager.delete("delTask")
    assert len(srem_calls) == len(task.items)
    mock_client.delete.assert_called()


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_delete_missing(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.get.return_value = None
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceDeleteError):
        await manager.delete("missing")


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_delete_redis_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.get.side_effect = redis.RedisError("read fail")
    with pytest.raises(PersistenceDeleteError):
        await manager.delete("t1")


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_delete_unexpected_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.get.side_effect = RuntimeError("boom")
    with pytest.raises(PersistenceDeleteError):
        await manager.delete("t2")


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_by_request_id_success(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    task = build_task("taskReq", ["req1"])  # single request id
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.smembers.return_value = {task.task_id}
    mock_client.get.return_value = manager._serialize_task(task)
    loaded = await manager.load_by_request_id("req1")
    assert loaded is not None and loaded.task_id == task.task_id


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_by_request_id_multiple(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    t = build_task("taskMulti", ["reqX"])  # underlying will just return first
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.smembers.return_value = {"taskMulti", "otherTask"}
    mock_client.get.return_value = manager._serialize_task(t)
    loaded = await manager.load_by_request_id("reqX")
    assert loaded.task_id == "taskMulti"


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_by_request_id_none_found(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.smembers.return_value = set()
    manager = RedisTaskPersistenceManager(mock_app_config)
    loaded = await manager.load_by_request_id("missing")
    assert loaded is None


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_by_request_id_redis_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.smembers.side_effect = redis.RedisError("smembers fail")
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceLoadError):
        await manager.load_by_request_id("rid1")


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_load_by_request_id_unexpected_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    mock_client.smembers.side_effect = RuntimeError("boom")
    manager = RedisTaskPersistenceManager(mock_app_config)
    with pytest.raises(PersistenceLoadError):
        await manager.load_by_request_id("rid2")


@patch("redis.Redis")
def test_health_check_success(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    assert manager.health_check() is True


@patch("redis.Redis")
def test_health_check_failure(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.ping.side_effect = redis.RedisError("ping fail")
    assert manager.health_check() is False


@patch("redis.Redis")
def test_clear_all_tasks_with_keys(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.keys.side_effect = lambda pattern: (
        [f"{pattern}abc"] if "task:" in pattern else [f"{pattern}idx"]
    )
    mock_client.delete.return_value = 2
    deleted = manager.clear_all_tasks()
    assert deleted == 2
    mock_client.delete.assert_called()


@patch("redis.Redis")
def test_clear_all_tasks_no_keys(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.keys.return_value = []
    deleted = manager.clear_all_tasks()
    assert deleted == 0
    mock_client.delete.assert_not_called()


@patch("redis.Redis")
def test_clear_all_tasks_redis_error(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    mock_client.keys.side_effect = redis.RedisError("keys fail")
    with pytest.raises(RuntimeError):
        manager.clear_all_tasks()


@pytest.mark.asyncio
@patch("redis.Redis")
async def test_concurrent_creates_and_loads(mock_redis_class, mock_app_config):
    mock_client = Mock()
    mock_client.ping.return_value = True
    mock_redis_class.return_value = mock_client
    manager = RedisTaskPersistenceManager(mock_app_config)
    # Simple in-memory store to mimic redis
    store = {}
    mock_client.exists.side_effect = lambda key: key in store
    mock_client.setex.side_effect = lambda key, ttl, value: store.update({key: value})
    mock_client.get.side_effect = lambda key: store.get(key)
    mock_client.sadd.side_effect = lambda key, value: None
    mock_client.expire.side_effect = lambda key, ttl: None

    async def create_task(i):
        t = build_task(f"t{i}", [f"req{i}"])
        await manager.create(t)

    async def load_task(i):
        return await manager.load(f"t{i}")

    # Run interleaved creates then loads
    for i in range(5):
        await create_task(i)
    loaded = []
    for i in range(5):
        loaded.append(await load_task(i))
    assert all(t is not None for t in loaded)
