# Task Persistence System

This document provides a comprehensive overview of the task persistence system for the Teal Agents framework, including detailed documentation of all classes, interfaces, and implementation patterns.

## Overview

The task persistence system provides a flexible, pluggable architecture for storing and retrieving agent tasks and their state. The system supports multiple storage backends through a factory pattern with dependency injection.

### Core Features

- **Pluggable Architecture**: Factory pattern with configurable implementations
- **Thread-Safe Operations**: Async-safe with proper locking mechanisms
- **In-Memory Storage** (default): Zero configuration, perfect for development
- **Redis Storage** (optional): Persistent, scalable, production-ready
- **Custom Storage**: Support for user-defined implementations
- **Request ID Indexing**: Fast lookups by request ID across all implementations

## Folder Structure

```text
persistence/
├── __init__.py                           # Package initialization (empty)
├── README.md                            # This documentation file
├── singleton.py                         # Thread-safe singleton metaclass
├── task_persistence_manager.py         # Abstract base class interface
├── in_memory_persistence_manager.py    # Default in-memory implementation
├── persistence_factory.py              # Factory pattern with dependency injection
└── custom/                              # Custom implementations directory
    └── example_redis_persistence.py    # Production-ready Redis implementation
```

## Core Classes Documentation

### 1. TaskPersistenceManager (Abstract Base Class)

**File**: `task_persistence_manager.py`

The abstract base class that defines the interface for all persistence implementations.

#### Methods

- **`async create(task: AgentTask) -> None`**
  - Creates a new task in the persistence layer
  - Should raise `PersistenceCreateError` if task already exists or on failure

- **`async load(task_id: str) -> AgentTask | None`**
  - Loads a task by its unique task ID
  - Returns `None` if task not found
  - Should raise `PersistenceLoadError` on failure

- **`async update(task: AgentTask) -> None`**
  - Updates an existing task in the persistence layer
  - Should raise `PersistenceUpdateError` if task doesn't exist or on failure

- **`async delete(task_id: str) -> None`**
  - Deletes a task by its unique task ID
  - Should raise `PersistenceDeleteError` if task doesn't exist or on failure

- **`async load_by_request_id(request_id: str) -> AgentTask | None`**
  - Loads a task by request ID (for tasks containing items with specific request IDs)
  - Returns the first matching task if multiple exist
  - Returns `None` if no task found

### 2. InMemoryPersistenceManager (Default Implementation)

**File**: `in_memory_persistence_manager.py`

Production-ready in-memory implementation with thread safety and request ID indexing.

#### Implementation Features

- **Thread Safety**: Uses `asyncio.Lock()` for concurrent access protection
- **Dual Indexing**: Primary storage by task_id + secondary index by request_id
- **Memory Efficient**: Automatic cleanup of empty index entries
- **Error Handling**: Comprehensive exception handling with custom error types

#### Internal Data Structures

- **`in_memory: dict[str, AgentTask]`**: Primary storage mapping task_id to AgentTask
- **`item_request_id_index: dict[str, set[str]]`**: Secondary index mapping request_id to set of task_ids

#### Thread Safety Implementation

```python
async with self._lock:
    # All operations are protected by asyncio.Lock
```

### 3. PersistenceFactory (Factory Pattern)

**File**: `persistence_factory.py`

Singleton factory responsible for creating and managing persistence manager instances with dependency injection support.

#### Key Features

- **Singleton Pattern**: Ensures single instance per application lifecycle
- **Dynamic Module Loading**: Loads custom implementations via `ModuleLoader`
- **Configuration-Driven**: Uses environment variables for custom implementations
- **Validation**: Ensures custom classes inherit from `TaskPersistenceManager`
- **Graceful Fallback**: Falls back to in-memory implementation if custom module fails

#### Configuration Methods

- **`_get_custom_persistence_config() -> tuple[str | None, str | None]`**
  - Retrieves module and class names from environment variables
  - Returns `(None, None)` if using default configuration

- **`_validate_custom_class()`**
  - Validates that custom class exists and inherits from `TaskPersistenceManager`
  - Raises appropriate exceptions for missing or invalid classes

#### Dependency Injection

The factory attempts to pass `app_config` to custom implementations:

```python
try:
    return custom_class(app_config=self.app_config)
except TypeError:
    # Fallback if app_config not accepted
    return custom_class()
```

### 4. Singleton (Metaclass)

**File**: `singleton.py`

Thread-safe singleton metaclass implementation using Python's `threading.Lock`.

#### Features

- **Thread Safety**: Uses `threading.Lock()` to prevent race conditions
- **Metaclass Pattern**: Implements singleton at the class level
- **Instance Caching**: Maintains `_instances` dictionary for created instances

#### Usage Pattern

```python
class MyClass(metaclass=Singleton):
    def __init__(self):
        # Initialization code
        pass
```

## Custom Implementations Directory

### RedisTaskPersistenceManager (Production Example)

**File**: `custom/example_redis_persistence.py`

A complete, production-ready Redis-based persistence implementation demonstrating advanced patterns.

#### Architecture Features

- **Connection Management**: Robust Redis connection with retry logic
- **Serialization**: JSON-based task serialization using Pydantic models
- **TTL Support**: Configurable time-to-live for all stored data
- **Index Management**: Maintains request_id to task_id mapping in Redis sets
- **Error Recovery**: Handles corrupted data with automatic cleanup
- **Health Monitoring**: Built-in health check capabilities

#### Configuration Environment Variables

```bash
TA_REDIS_HOST        # Redis server hostname (default: localhost)
TA_REDIS_PORT        # Redis server port (default: 6379)
TA_REDIS_DB          # Redis database number (default: 0)
TA_REDIS_TTL         # Time-to-live in seconds (default: 3600)
TA_REDIS_PWD         # Redis password (optional)
TA_REDIS_SSL         # Enable SSL connection (default: false)
```

#### Redis Key Patterns

- **Task Storage**: `task_persistence:task:{task_id}`
- **Request Index**: `task_persistence:request_index:{request_id}`

#### Advanced Methods

- **`health_check() -> bool`**: Tests Redis connectivity
- **`clear_all_tasks() -> int`**: Utility method for testing/cleanup
- **`_serialize_task(task: AgentTask) -> str`**: JSON serialization
- **`_deserialize_task(task_str: str) -> AgentTask`**: JSON deserialization

#### Error Handling Strategy

```python
try:
    # Redis operation
except redis.RedisError as e:
    raise PersistenceCreateError(f"Redis error: {e}") from e
except json.JSONDecodeError as e:
    # Handle corrupted data with cleanup
    self.redis_client.delete(task_key)
    raise PersistenceLoadError(f"Corrupted data: {e}") from e
```

## Configuration System

### Environment Variables

The persistence system uses the following environment variables:

- **`TA_PERSISTENCE_MODULE`**: Path to custom task persistence module
- **`TA_PERSISTENCE_CLASS`**: Class name for custom implementation

### Configuration Examples

#### Development (Default - In-Memory)

```bash
# No configuration needed - uses in-memory storage
```

#### Production with Redis

```bash
export TA_PERSISTENCE_MODULE=src/sk_agents/persistence/custom/example_redis_persistence.py
export TA_PERSISTENCE_CLASS=RedisTaskPersistenceManager
export TA_REDIS_HOST=redis.production.com
export TA_REDIS_PORT=6379
export TA_REDIS_PWD=secure_password
export TA_REDIS_SSL=true
export TA_REDIS_TTL=7200
```

#### Custom Implementation

```bash
export TA_PERSISTENCE_MODULE=my_custom_module.py
export TA_PERSISTENCE_CLASS=MyCustomPersistenceManager
```

## Usage Patterns

### Basic Usage

```python
from ska_utils import AppConfig
from sk_agents.persistence.persistence_factory import PersistenceFactory
from sk_agents.tealagents.models import AgentTask

# Get task persistence manager
app_config = AppConfig()
factory = PersistenceFactory(app_config)
persistence_manager = factory.get_persistence_manager()

# Store, retrieve, and manage task data
await persistence_manager.create(agent_task)
retrieved_task = await persistence_manager.load("task_id_123")
await persistence_manager.update(agent_task)
await persistence_manager.delete("task_id_123")

# Load by request ID (useful for resuming workflows)
task = await persistence_manager.load_by_request_id("request_123")
```

### Advanced Usage with Error Handling

```python
from sk_agents.exceptions import PersistenceCreateError, PersistenceLoadError

try:
    await persistence_manager.create(task)
except PersistenceCreateError as e:
    logger.error(f"Failed to create task: {e.message}")
    # Handle creation failure

try:
    task = await persistence_manager.load(task_id)
    if task is None:
        logger.info(f"Task {task_id} not found")
    else:
        # Process loaded task
        pass
except PersistenceLoadError as e:
    logger.error(f"Failed to load task: {e.message}")
```

## Creating Custom Implementations

### Step 1: Implement the Interface

Create a new class that inherits from `TaskPersistenceManager`:

```python
from sk_agents.persistence.task_persistence_manager import TaskPersistenceManager
from sk_agents.tealagents.models import AgentTask
from sk_agents.exceptions import (
    PersistenceCreateError,
    PersistenceDeleteError,
    PersistenceLoadError,
    PersistenceUpdateError,
)

class MyCustomTaskPersistenceManager(TaskPersistenceManager):
    def __init__(self, app_config=None):
        # Initialize your storage backend
        self.storage = self._initialize_storage(app_config)
    
    async def create(self, task: AgentTask) -> None:
        try:
            # Your implementation
            if await self._task_exists(task.task_id):
                raise PersistenceCreateError(
                    f"Task {task.task_id} already exists"
                )
            await self._store_task(task)
        except Exception as e:
            raise PersistenceCreateError(f"Create failed: {e}") from e

    async def load(self, task_id: str) -> AgentTask | None:
        try:
            return await self._retrieve_task(task_id)
        except Exception as e:
            raise PersistenceLoadError(f"Load failed: {e}") from e

    async def update(self, task: AgentTask) -> None:
        try:
            if not await self._task_exists(task.task_id):
                raise PersistenceUpdateError(
                    f"Task {task.task_id} does not exist"
                )
            await self._update_task(task)
        except Exception as e:
            raise PersistenceUpdateError(f"Update failed: {e}") from e

    async def delete(self, task_id: str) -> None:
        try:
            if not await self._task_exists(task_id):
                raise PersistenceDeleteError(
                    f"Task {task_id} does not exist"
                )
            await self._remove_task(task_id)
        except Exception as e:
            raise PersistenceDeleteError(f"Delete failed: {e}") from e

    async def load_by_request_id(self, request_id: str) -> AgentTask | None:
        try:
            task_ids = await self._find_tasks_by_request_id(request_id)
            if not task_ids:
                return None
            return await self.load(task_ids[0])
        except Exception as e:
            raise PersistenceLoadError(f"Load by request_id failed: {e}") from e
```

### Step 2: Configuration

Set the environment variables to use your custom implementation:

```bash
export TA_PERSISTENCE_MODULE=path/to/your/custom_module.py
export TA_PERSISTENCE_CLASS=MyCustomTaskPersistenceManager
```

### Step 3: Integration

The factory will automatically load and validate your implementation when the application starts.

## Error Handling

The persistence system uses custom exception types for different failure scenarios:

- **`PersistenceCreateError`**: Task creation failures
- **`PersistenceLoadError`**: Task retrieval failures
- **`PersistenceUpdateError`**: Task update failures
- **`PersistenceDeleteError`**: Task deletion failures

All implementations should raise these specific exceptions to maintain consistent error handling across the system.

## Testing Considerations

When implementing custom persistence managers:

1. **Unit Tests**: Test all CRUD operations with various edge cases
2. **Concurrency Tests**: Verify thread safety with concurrent operations
3. **Error Scenarios**: Test network failures, corrupted data, etc.
4. **Performance Tests**: Measure latency and throughput under load
5. **Integration Tests**: Test with actual AgentTask objects

Example test pattern:

```python
import pytest
from sk_agents.tealagents.models import AgentTask

@pytest.mark.asyncio
async def test_create_and_load():
    persistence_manager = MyCustomPersistenceManager()
    
    # Create test task
    task = AgentTask(task_id="test_123", ...)
    await persistence_manager.create(task)
    
    # Verify retrieval
    loaded_task = await persistence_manager.load("test_123")
    assert loaded_task is not None
    assert loaded_task.task_id == "test_123"
```

## Best Practices

1. **Thread Safety**: Always implement proper locking for concurrent access
2. **Error Handling**: Use the standard exception types for consistency
3. **Resource Management**: Properly close connections and clean up resources
4. **Configuration**: Support dependency injection via `app_config` parameter
5. **Logging**: Include comprehensive logging for debugging and monitoring
6. **Validation**: Validate input parameters and handle edge cases
7. **Documentation**: Document configuration requirements and usage patterns
