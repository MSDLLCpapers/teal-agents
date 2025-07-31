# Phase 4 Implementation Plan: Plugin Catalog

This document outlines the development tasks to introduce a plugin catalog. This catalog will serve as a centralized repository for tool definitions and their associated metadata, such as governance policies (e.g., HITL requirements) and authentication details.

This plan establishes an abstraction layer for the catalog, with an initial implementation that reads from a local JSON file.

## Task 1: Plugin Catalog Data Models

**Objective:** Define the core Pydantic models that represent plugins, tools, and their metadata.

- **File to Create:** `src/sk_agents/plugincatalog/models.py`
- **Details:** Implement the following Pydantic models. We will use discriminated unions to handle different plugin and auth types.

```python
from typing import List, Literal, Union
from pydantic import BaseModel, Field

# PluginType Models
class CodePluginType(BaseModel):
    type_name: Literal["code"] = "code"

class McpPluginType(BaseModel):
    type_name: Literal["mcp"] = "mcp"
    # Future metadata for MCP plugins will go here

PluginType = Union[CodePluginType, McpPluginType]

# Governance Model
class Governance(BaseModel):
    requires_hitl: bool = False
    cost: Literal["low", "medium", "high"]
    data_sensitivity: Literal["public", "proprietary", "confidential", "sensitive"]

# PluginAuth Models
class Oauth2PluginAuth(BaseModel):
    auth_type: Literal["oauth2"] = "oauth2"
    auth_server: str
    scopes: List[str]

PluginAuth = Union[Oauth2PluginAuth]

# Core Plugin Models
class PluginTool(BaseModel):
    tool_id: str # Unique identifier, e.g., "Shell-execute"
    name: str
    description: str
    governance: Governance

class Plugin(BaseModel):
    plugin_id: str # e.g., "Shell"
    name: str
    description: str
    version: str
    owner: str
    plugin_type: PluginType = Field(..., discriminator="type_name")
    auth: PluginAuth | None = Field(None, discriminator="auth_type")
    tools: List[PluginTool]

class PluginCatalogDefinition(BaseModel):
    plugins: List[Plugin]
```

## Task 2: Plugin Catalog Abstraction and Factory

**Objective:** Create an abstract base class for the catalog and a singleton factory to instantiate the configured provider.

- **Files to Create:**
    - `src/sk_agents/plugincatalog/plugin_catalog.py`
    - `src/sk_agents/plugincatalog/plugin_catalog_factory.py`
- **Details:**
    1.  **Define `PluginCatalog` ABC:** This class will define the contract for all catalog implementations.
        ```python
        # src/sk_agents/plugincatalog/plugin_catalog.py
        from abc import ABC, abstractmethod
        from .models import Plugin, PluginTool

        class PluginCatalog(ABC):
            @abstractmethod
            def get_plugin(self, plugin_id: str) -> Plugin | None:
                ...

            @abstractmethod
            def get_tool(self, tool_id: str) -> PluginTool | None:
                ...
        ```
    2.  **Implement `PluginCatalogFactory`:** This factory will be a singleton responsible for creating the catalog instance based on environment variables. It should use the `Singleton` class from the `ska-utils` package.
        - It will read `TA_PLUGIN_CATALOG_MODULE` and `TA_PLUGIN_CATALOG_CLASS` to dynamically import and instantiate the catalog provider.

## Task 3: `LocalPluginCatalog` Implementation

**Objective:** Create a file-based implementation of the `PluginCatalog` for initial development and testing.

- **File to Create:** `src/sk_agents/plugincatalog/local_plugin_catalog.py`
- **Details:**
    1.  **Implement `LocalPluginCatalog`:**
        - Inherit from `PluginCatalog`.
        - In the constructor, read the JSON file path from the `TA_PLUGIN_CATALOG_FILE` environment variable.
        - Load and parse the JSON file into the Pydantic models defined in Task 1.
        - Create internal dictionaries to provide efficient lookups for `get_plugin()` and `get_tool()`.
    2.  **Example `catalog.json`:**
        ```json
        {
          "plugins": [
            {
              "plugin_id": "Shell",
              "name": "Shell",
              "description": "Executes shell commands.",
              "version": "1.0",
              "owner": "system",
              "plugin_type": { "type_name": "code" },
              "auth": null,
              "tools": [
                {
                  "tool_id": "Shell-execute",
                  "name": "execute",
                  "description": "Executes a command in the shell.",
                  "governance": {
                    "requires_hitl": true,
                    "cost": "high",
                    "data_sensitivity": "sensitive"
                  }
                }
              ]
            }
          ]
        }
        ```

## Task 4: Integrate Catalog with HITL Manager

**Objective:** Update the HITL logic to use the plugin catalog to decide if an intervention is required.

- **File to Modify:** `src/sk_agents/hitl/hitl_manager.py`
- **Details:**
    - The `check_for_intervention` function will be updated to use the catalog. The hardcoded logic will be removed.
    - The function will construct a `tool_id` from the `FunctionCallContent` provided by the kernel. The convention will be `{plugin_name}-{function_name}`.

    ```python
    # src/sk_agents/hitl/hitl_manager.py
    from semantic_kernel.contents.function_call_content import FunctionCallContent
    from sk_agents.plugincatalog import plugin_catalog_factory

    def check_for_intervention(tool_call: FunctionCallContent) -> bool:
        """
        Checks the plugin catalog to determine if a tool call requires
        Human-in-the-Loop intervention.
        """
        catalog = plugin_catalog_factory.get_instance()
        if not catalog:
            # Fallback if catalog is not configured
            return False

        tool_id = f"{tool_call.plugin_name}-{tool_call.function_name}"
        tool = catalog.get_tool(tool_id)

        if tool:
            print(f"HITL Check: Intercepted call to {tool_id}. Requires HITL: {tool.governance.requires_hitl}")
            return tool.governance.requires_hitl

        # Default to no intervention if tool is not in the catalog
        return False
    ```

## Task 5: Testing Strategy

**Objective:** Ensure the plugin catalog is correctly implemented and integrated.

- **Files to Create/Modify:**
    - `demos/catalog.json` (a sample catalog for testing)
    - `tests/test_plugin_catalog.py` (new test file)
    - `tests/test_tealagents_handler.py` (modify existing tests)
- **Details:**
    1.  **Unit Tests (`test_plugin_catalog.py`):**
        - Test `LocalPluginCatalog` can correctly load, parse, and validate a `catalog.json` file.
        - Test successful lookups via `get_plugin()` and `get_tool()`.
        - Test that lookups for non-existent IDs return `None`.
        - Test the `PluginCatalogFactory` correctly instantiates the `LocalPluginCatalog`.
    2.  **Integration Tests (`test_tealagents_handler.py`):**
        - Modify the existing HITL tests.
        - Point `TA_PLUGIN_CATALOG_FILE` to a test-specific catalog file.
        - Verify that the HITL "pause" flow is triggered if and only if a tool with `requires_hitl: true` is called.
        - Verify that tools not in the catalog or marked as `false` proceed without intervention.

## Task 6: Environment Variables and Configuration

**Objective:** Document the new environment variables for configuring the plugin catalog.

- **Details:** The application will now rely on the following environment variables:
    - `TA_PLUGIN_CATALOG_MODULE`: The Python module path for the catalog implementation.
        - **Default:** `sk_agents.plugincatalog.local_plugin_catalog`
    - `TA_PLUGIN_CATALOG_CLASS`: The class name of the catalog implementation.
        - **Default:** `LocalPluginCatalog`
    - `TA_PLUGIN_CATALOG_FILE`: The absolute path to the JSON file containing plugin definitions (used by `LocalPluginCatalog`).
        - **Default:** `/app/catalog.json` (or another suitable default path)
