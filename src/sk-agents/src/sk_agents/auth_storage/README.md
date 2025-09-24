# Authentication Storage System

This document describes the authentication storage system for the Teal Agents framework.

## Overview

The authentication storage system securely stores OAuth 2.0 and other authentication credentials. It provides:

- **In-Memory Storage** (default): Zero configuration, perfect for development
- **Redis Storage** (optional): Persistent, scalable, production-ready
- **Custom Storage**: Support for user-defined implementations

## Configuration

### Environment Variables

- `TA_AUTH_STORAGE_MANAGER_MODULE`: Path to custom auth storage module
- `TA_AUTH_STORAGE_MANAGER_CLASS`: Class name for custom implementation

### Examples

#### Development (Default)
```bash
# No configuration needed - uses in-memory storage
```

#### Production with Redis
```bash
export TA_AUTH_STORAGE_MANAGER_MODULE=src/sk_agents/auth_storage/custom/example_redis_auth_storage.py
export TA_AUTH_STORAGE_MANAGER_CLASS=RedisSecureAuthStorageManager
export TA_REDIS_HOST=redis.production.com
export TA_REDIS_PORT=6379
export TA_REDIS_PWD=secure_password
```

## Usage

```python
from ska_utils import AppConfig
from sk_agents.auth_storage.auth_storage_factory import AuthStorageFactory
from sk_agents.auth_storage.models import OAuth2AuthData

# Get auth storage manager
app_config = AppConfig()
factory = AuthStorageFactory(app_config)
auth_storage = factory.get_auth_storage_manager()

# Store, retrieve, and delete auth data
auth_storage.store("user123", "tool_a", auth_data)
retrieved_data = auth_storage.retrieve("user123", "tool_a")
auth_storage.delete("user123", "tool_a")
```

## Custom Implementation

Create custom storage by extending `SecureAuthStorageManager`:

```python
from sk_agents.auth_storage.secure_auth_storage_manager import SecureAuthStorageManager

class MyCustomAuthStorageManager(SecureAuthStorageManager):
    def store(self, user_id: str, key: str, data: AuthData) -> None:
        # Your implementation
        pass

    def retrieve(self, user_id: str, key: str) -> AuthData | None:
        # Your implementation
        return None

    def delete(self, user_id: str, key: str) -> None:
        # Your implementation
        pass
```
