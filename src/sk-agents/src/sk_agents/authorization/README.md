# Authorization Module

This module provides a flexible authorization system for the SK Agents framework. It implements a factory pattern to dynamically load and manage request authorization mechanisms, with support for pluggable authorization strategies.

## Architecture Overview

The authorization module follows a factory pattern with an abstract base class that defines the authorization interface. This design allows for easy extension and customization of authorization mechanisms while maintaining a consistent API.

## Files and Classes

### `__init__.py`

Empty initialization file that marks this directory as a Python package.

### `request_authorizer.py`

#### `RequestAuthorizer` (Abstract Base Class)

An abstract base class that defines the contract for all authorization implementations.

**Purpose**: Provides a standardized interface for authorization mechanisms across the application.

**Key Method**:

- `authorize_request(auth_header: str) -> str`: Abstract method that validates an authorization header and returns a unique user identifier.

**Parameters**:

- `auth_header`: The value of the 'Authorization' HTTP header (typically "Bearer token" format)

**Returns**:

- A unique string identifier for the authenticated user (e.g., user ID, username, email)

**Raises**:

- `ValueError`: For missing, malformed, or invalid authorization headers
- `AuthenticationError`: (Optional) For authentication failures in implementations

**Usage**: All custom authorization implementations must inherit from this class and implement the `authorize_request` method.

### `dummy_authorizer.py`

#### `DummyAuthorizer` (Concrete Implementation)

A simple test/development implementation of the `RequestAuthorizer` interface.

**Purpose**: Provides a no-op authorization mechanism for development, testing, or scenarios where authentication is not required.

**Behavior**:

- Always returns "dummyuser" regardless of the input authorization header
- Does not perform any actual validation or authentication
- Useful for development environments or testing scenarios

**Implementation**:

```python
async def authorize_request(self, auth_header: str) -> str:
    return "dummyuser"
```

**Use Cases**:

- Local development without authentication setup
- Testing environments
- Placeholder implementation during development

### `singleton.py`

#### `Singleton` (Metaclass)

A thread-safe implementation of the Singleton design pattern using a metaclass.

**Purpose**: Ensures that only one instance of a class exists throughout the application lifecycle while being thread-safe.

**Features**:

- **Thread Safety**: Uses `threading.Lock()` to prevent race conditions in multi-threaded environments
- **Instance Management**: Maintains a dictionary of class instances (`_instances`)
- **Metaclass Implementation**: Implemented as a metaclass (`ABCMeta` subclass) for clean integration

**Key Components**:

- `_instances`: Class-level dictionary storing singleton instances
- `_lock`: Threading lock for thread-safe instance creation
- `__call__`: Overridden method that controls instance creation

**Usage**: Classes that need singleton behavior inherit this as their metaclass:

```python
class MyClass(metaclass=Singleton):
    pass
```

**Thread Safety**: The implementation ensures that even in multi-threaded environments, only one instance of each class is created.

### `authorizer_factory.py`

#### `AuthorizerFactory` (Singleton Factory)

A factory class that dynamically loads and creates authorization implementations based on configuration.

**Purpose**: Provides a centralized way to create and manage authorization instances while supporting dynamic loading of custom authorization implementations.

**Design Pattern**: Factory pattern combined with Singleton pattern for application-wide consistency.

**Key Features**:

- **Dynamic Loading**: Loads authorization classes from modules specified by file paths in configuration
- **Type Safety**: Validates that loaded classes are proper `RequestAuthorizer` subclasses
- **Configuration-Driven**: Uses environment variables to determine which authorization implementation to use
- **Singleton**: Ensures consistent authorization behavior across the application

**Constructor Parameters**:

- `app_config`: An `AppConfig` instance containing application configuration

**Key Methods**:

##### `get_authorizer() -> RequestAuthorizer`

Returns an instance of the configured authorization class.

**Returns**: A configured `RequestAuthorizer` implementation

##### `_get_authorizer_config() -> tuple[str, str]` (Private)

Retrieves the module and class names from configuration.

**Returns**: Tuple containing (module_name, class_name)

**Raises**:

- `ValueError`: If required environment variables are not set

**Configuration Requirements**:

- `TA_AUTHORIZER_MODULE`: Environment variable specifying the file path to the module containing the authorization class (e.g., `src/sk_agents/authorization/dummy_authorizer.py`)
- `TA_AUTHORIZER_CLASS`: Environment variable specifying the authorization class name

**Error Handling**:

- `ImportError`: Raised if the specified module cannot be loaded or the class is not found
- `TypeError`: Raised if the loaded class is not a subclass of `RequestAuthorizer`
- `ValueError`: Raised if required configuration is missing

**Usage Example**:

```python
# Configuration (environment variables)
TA_AUTHORIZER_MODULE = "src/sk_agents/authorization/dummy_authorizer.py"
TA_AUTHORIZER_CLASS = "DummyAuthorizer"

# Usage
factory = AuthorizerFactory(app_config)
authorizer = factory.get_authorizer()
user_id = await authorizer.authorize_request("Bearer token123")
```

## Configuration

The authorization system is configured through environment variables:

- **`TA_AUTHORIZER_MODULE`**: Specifies the file path to the Python module containing the authorization implementation (e.g., `src/sk_agents/authorization/dummy_authorizer.py`)
- **`TA_AUTHORIZER_CLASS`**: Specifies the class name within the module that implements authorization

## Usage Patterns

### 1. Using the Default (Dummy) Authorization

```python
# Set environment variables
TA_AUTHORIZER_MODULE = "src/sk_agents/authorization/dummy_authorizer.py"
TA_AUTHORIZER_CLASS = "DummyAuthorizer"

# Create factory and get authorizer
factory = AuthorizerFactory(app_config)
authorizer = factory.get_authorizer()
```

### 2. Implementing Custom Authorization

```python
# Create custom authorizer
class MyCustomAuthorizer(RequestAuthorizer):
    async def authorize_request(self, auth_header: str) -> str:
        # Custom validation logic
        if not auth_header.startswith("Bearer "):
            raise ValueError("Invalid authorization header format")
        
        token = auth_header[7:]  # Remove "Bearer " prefix
        # Validate token and return user ID
        return validate_and_extract_user_id(token)

# Configure to use custom authorizer
TA_AUTHORIZER_MODULE = "my_module/custom_auth.py"
TA_AUTHORIZER_CLASS = "MyCustomAuthorizer"
```

### 3. Integration in Web Applications

```python
# In request handlers
async def protected_endpoint(request):
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise ValueError("Authorization header required")
    
    factory = AuthorizerFactory(app_config)
    authorizer = factory.get_authorizer()
    user_id = await authorizer.authorize_request(auth_header)
    
    # Proceed with authorized request
    return handle_request_for_user(user_id)
```

## Design Benefits

1. **Flexibility**: Easy to swap authorization mechanisms without code changes
2. **Extensibility**: Simple to add new authorization strategies
3. **Testability**: Dummy implementation available for testing
4. **Configuration-Driven**: No hardcoded authorization logic
5. **Thread Safety**: Singleton implementation ensures consistent behavior
6. **Type Safety**: Factory validates loaded classes at runtime

## Dependencies

- `ska_utils.AppConfig`: For configuration management
- `ska_utils.ModuleLoader`: For dynamic module loading
- `sk_agents.configs`: For configuration constants
- `threading`: For thread-safe singleton implementation
- `abc`: For abstract base class definition

## Thread Safety

The module is designed to be thread-safe:

- The `Singleton` metaclass uses threading locks to prevent race conditions
- The `AuthorizerFactory` is a singleton, ensuring consistent authorization across threads
- Authorization instances can be safely shared across multiple threads

## Error Handling

The module provides comprehensive error handling:

- **Configuration Errors**: Clear messages for missing environment variables
- **Import Errors**: Detailed error messages for module loading failures
- **Type Errors**: Validation that loaded classes implement the correct interface
- **Authorization Errors**: Proper propagation of authentication failures