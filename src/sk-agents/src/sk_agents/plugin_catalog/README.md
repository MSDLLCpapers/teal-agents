# Plugin Catalog Module

The Plugin Catalog module provides a comprehensive system for managing, cataloging, and accessing plugins and their associated tools within the Teal Agents framework. This module implements a flexible architecture that supports different plugin types, governance controls, authentication mechanisms, and data loading strategies.

## Module Overview

The plugin catalog system is designed to:

- Provide a standardized way to define and catalog plugins
- Implement governance controls for plugin tools (cost, data sensitivity, human-in-the-loop requirements)
- Support different plugin types (code-based, MCP-based)
- Enable dynamic loading and configuration of plugin catalogs
- Maintain a registry of available tools with their metadata

## File Structure and Components

### 1. `models.py` - Data Models and Schema Definitions

This file contains all Pydantic data models that define the structure and validation rules for the plugin catalog system.

#### Core Classes

**Plugin Type Models:**

- `CodePluginType`: Represents plugins that contain executable code
  - `type_name`: Literal["code"] - Identifies this as a code-based plugin

- `McpPluginType`: Represents Model Context Protocol (MCP) plugins
  - `type_name`: Literal["mcp"] - Identifies this as an MCP plugin
  - Future-proofed for additional MCP-specific metadata

- `PluginType`: Union type that can be either CodePluginType or McpPluginType

**Governance Model:**

- `Governance`: Defines security and operational controls for plugin tools
  - `requires_hitl`: Boolean flag indicating if human-in-the-loop approval is required
  - `cost`: Enum ["low", "medium", "high"] - Resource cost classification
  - `data_sensitivity`: Enum ["public", "proprietary", "confidential", "sensitive"] - Data sensitivity level

**Authentication Models:**

- `Oauth2PluginAuth`: OAuth2 authentication configuration
  - `auth_type`: Literal["oauth2"] - Authentication method identifier
  - `auth_server`: Server URL for OAuth2 authentication
  - `scopes`: List of OAuth2 scopes required

- `PluginAuth`: Union type for authentication methods (currently only OAuth2)

**Core Plugin Models:**

- `PluginTool`: Represents an individual tool within a plugin
  - `tool_id`: Unique identifier (e.g., "Shell-execute")
  - `name`: Human-readable tool name
  - `description`: Tool functionality description
  - `governance`: Governance controls for the tool
  - `auth`: Optional authentication requirements

- `Plugin`: Represents a complete plugin with its tools
  - `plugin_id`: Unique plugin identifier
  - `name`: Human-readable plugin name
  - `description`: Plugin functionality description
  - `version`: Plugin version string
  - `owner`: Plugin owner/maintainer
  - `plugin_type`: Type of plugin (code or MCP)
  - `tools`: List of tools provided by the plugin

- `PluginCatalogDefinition`: Top-level container for plugin catalog data
  - `plugins`: List of all plugins in the catalog

### 2. `plugin_catalog.py` - Abstract Base Class

This file defines the abstract interface that all plugin catalog implementations must follow.

#### Interface Definition

**PluginCatalog (ABC):**

- Abstract base class defining the contract for plugin catalog implementations
- **Methods:**
  - `get_plugin(plugin_id: str) -> Plugin | None`: Retrieve a plugin by its ID
  - `get_tool(tool_id: str) -> PluginTool | None`: Retrieve a tool by its ID

This abstraction allows for different storage backends (file-based, database, remote API, etc.) while maintaining a consistent interface.

### 3. `local_plugin_catalog.py` - File-Based Implementation

This file contains the concrete implementation of the plugin catalog that loads plugins from local JSON files.

#### Implementation Details

**FileBasedPluginCatalog:**

- Concrete implementation of PluginCatalog that loads from JSON files
- **Constructor Parameters:**
  - `app_config`: AppConfig instance for configuration management

- **Instance Variables:**
  - `app_config`: Configuration manager
  - `catalog_path`: Path to the JSON catalog file
  - `_plugins`: Dictionary mapping plugin IDs to Plugin objects
  - `_tools`: Dictionary mapping tool IDs to PluginTool objects

- **Methods:**
  - `get_plugin(plugin_id: str) -> Plugin | None`: Retrieves plugin from internal cache
  - `get_tool(tool_id: str) -> PluginTool | None`: Retrieves tool from internal cache
  - `_load_plugins()`: Private method that loads and validates plugins from JSON file

- **Error Handling:**
  - Validates JSON structure against Pydantic models
  - Raises `PluginCatalogDefinitionException` for validation errors
  - Raises `PluginFileReadException` for file I/O errors

### 4. `plugin_catalog_factory.py` - Singleton Factory

This file implements a factory pattern with singleton behavior for creating plugin catalog instances.

#### Factory Implementation

**PluginCatalogFactory:**

- Singleton factory that creates and manages plugin catalog instances
- Uses environment variables to determine which catalog implementation to load
- **Singleton Behavior:** Ensures only one factory instance exists per application

- **Instance Variables:**
  - `app_config`: Configuration manager
  - `_catalog_instance`: Cached catalog instance

- **Methods:**
  - `get_catalog() -> PluginCatalog`: Returns the catalog instance, creating it if needed
  - `_create_catalog() -> PluginCatalog`: Creates new catalog instance based on environment configuration

- **Configuration:**
  - Uses `TA_PLUGIN_CATALOG_MODULE` environment variable to specify the module
  - Uses `TA_PLUGIN_CATALOG_CLASS` environment variable to specify the class name
  - Dynamically loads and instantiates the specified catalog class

- **Error Handling:**
  - Validates that environment variables are set
  - Ensures the specified class inherits from PluginCatalog
  - Handles import and instantiation errors gracefully

### 5. `catalog.json` - Plugin Definitions

This JSON file contains the actual plugin and tool definitions used by the file-based catalog implementation.

#### Plugin Structure

The file contains a `plugins` array with the following sample plugins:

**sensitive_plugin:**

- Plugin for executing sensitive shell commands
- Tools: `delete_user_data` - requires human approval due to high sensitivity

**finance_plugin:**

- Plugin for financial operations
- Tools:
  - `initiate_transfer` - requires human approval for financial transactions
  - `get_balance` - low-cost balance inquiry operation

**admin_tools:**

- Administrative system tools
- Tools: `shutdown_service` - requires human approval for service management

**utility_plugin:**

- General utility operations
- Tools: `ShellCommand` - general shell command execution with approval requirements

Each plugin includes:

- Unique identification and metadata
- Version and ownership information
- Plugin type classification
- List of available tools with their governance requirements

## Usage Patterns

### 1. Basic Usage

```python
from sk_agents.plugin_catalog.plugin_catalog_factory import PluginCatalogFactory

# Get the catalog instance
factory = PluginCatalogFactory()
catalog = factory.get_catalog()

# Retrieve a specific plugin
plugin = catalog.get_plugin("finance_plugin")

# Retrieve a specific tool
tool = catalog.get_tool("finance_plugin-get_balance")
```

### 2. Governance Checks

```python
tool = catalog.get_tool("sensitive_plugin-delete_user_data")
if tool and tool.governance.requires_hitl:
    # Request human approval before execution
    await request_human_approval(tool)
```

### 3. Custom Catalog Implementation

```python
from sk_agents.plugin_catalog.plugin_catalog import PluginCatalog

class DatabasePluginCatalog(PluginCatalog):
    def get_plugin(self, plugin_id: str) -> Plugin | None:
        # Custom implementation using database
        pass
    
    def get_tool(self, tool_id: str) -> PluginTool | None:
        # Custom implementation using database
        pass
```

## Configuration

The module uses environment variables for configuration:

- `TA_PLUGIN_CATALOG_MODULE`: Python module containing the catalog class
- `TA_PLUGIN_CATALOG_CLASS`: Class name within the module
- `TA_PLUGIN_CATALOG_FILE`: Path to the JSON catalog file (for file-based implementation)

## Security Considerations

The plugin catalog system includes several security features:

1. **Governance Controls**: Each tool specifies its risk level and requirements
2. **Human-in-the-Loop**: Critical operations can require human approval
3. **Data Sensitivity Classification**: Tools are classified by data sensitivity
4. **Authentication Support**: OAuth2 and other auth methods can be specified
5. **Validation**: All plugin definitions are validated against strict schemas

## Extensibility

The modular design allows for easy extension:

1. **New Plugin Types**: Add new plugin type models to support additional architectures
2. **Additional Auth Methods**: Extend the PluginAuth union with new authentication types
3. **Custom Catalogs**: Implement the PluginCatalog interface for different storage backends
4. **Enhanced Governance**: Add new governance controls and validation rules

## Dependencies

- `pydantic`: For data validation and serialization
- `ska_utils`: For configuration management and module loading
- `pathlib`: For file system operations
- `json`: For JSON file parsing
- `typing`: For type hints and annotations

This plugin catalog system provides a robust foundation for managing plugins in the Teal Agents framework, with strong typing, validation, and governance controls to ensure secure and reliable plugin execution.
