# Task Persistence System

This document describes the task persistence system for the Teal Agents framework.

## Overview

The task persistence system securely stores agent tasks and their state. It provides:

- **In-Memory Storage** (default): Zero configuration, perfect for development
- **Redis Storage** (optional): Persistent, scalable, production-ready
- **Custom Storage**: Support for user-defined implementations

## Configuration

### Environment Variables

- `TA_PERSISTENCE_MODULE`: Path to custom task persistence module
- `TA_PERSISTENCE_CLASS`: Class name for custom implementation

### Examples

#### Development (Default)
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
```

## Usage

```python
from ska_utils import AppConfig
from sk_agents.persistence.persistence_factory import PersistenceFactory
from sk_agents.tealagents.models import AgentTask

# Get task persistence manager
app_config = AppConfig()
factory = PersistenceFactory(app_config)
persistence_manager = factory.get_persistence_manager()

# Store, retrieve, and delete task data
await persistence_manager.create(agent_task)
retrieved_task = await persistence_manager.load("task_id_123")
await persistence_manager.update(agent_task)
await persistence_manager.delete("task_id_123")
```

## Custom Implementation

Create custom storage by extending `TaskPersistenceManager`:

```python
from sk_agents.persistence.task_persistence_manager import TaskPersistenceManager

class MyCustomTaskPersistenceManager(TaskPersistenceManager):
    async def create(self, task: AgentTask) -> None:
        # Your implementation
        pass

    async def load(self, task_id: str) -> AgentTask | None:
        # Your implementation
        return None

    async def update(self, task: AgentTask) -> None:
        # Your implementation
        pass

    async def delete(self, task_id: str) -> None:
        # Your implementation
        pass

    async def load_by_request_id(self, request_id: str) -> AgentTask | None:
        # Your implementation
        return None
```
