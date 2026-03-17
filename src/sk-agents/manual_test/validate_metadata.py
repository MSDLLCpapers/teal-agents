"""
Manual Validation Script for /metadata Endpoint
================================================

This script validates the /metadata endpoint works correctly for both
AppV1 (skagents) and AppV3 (tealagents) WITHOUT needing any external
services (no OpenAI, no Redis, no real agent running).

It directly constructs the FastAPI app with the metadata route and
tests it using FastAPI's TestClient.

HOW TO RUN:
-----------
    cd teal-agents/src/sk-agents
    uv run python manual_test/validate_metadata.py

WHAT IT CHECKS:
---------------
1. AppV1 (skagents/v1) metadata endpoint returns correct data
2. AppV3 (tealagents/v1alpha1) metadata endpoint returns correct data
3. Response format matches the AgentMetadata schema
4. All four required fields are present: agent_name, description, model, plugins
"""

import json
import sys

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sk_agents.ska_types import BaseConfig, ConfigMetadata, ConfigSkill
from sk_agents.skagents.v1.chat.config import Spec as V1Spec
from sk_agents.skagents.v1.config import AgentConfig as V1AgentConfig
from sk_agents.tealagents.v1alpha1.agent.config import Spec as V3Spec
from sk_agents.tealagents.v1alpha1.config import AgentConfig as V3AgentConfig
from sk_agents.utility_routes import UtilityRoutes

PASS = "\033[92m✅ PASS\033[0m"
FAIL = "\033[91m❌ FAIL\033[0m"


def print_header(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_response(data: dict):
    print(f"  Response JSON:")
    print(f"  {json.dumps(data, indent=4)}")


def check(label: str, condition: bool, actual=None, expected=None):
    if condition:
        print(f"  {PASS} {label}")
    else:
        print(f"  {FAIL} {label}")
        if actual is not None:
            print(f"       Expected: {expected}")
            print(f"       Actual:   {actual}")
    return condition


def test_appv1_metadata():
    """Test /metadata endpoint for AppV1 (skagents/v1) config."""
    print_header("TEST 1: AppV1 (skagents/v1) - WeatherBot with plugins")

    # Build a real V1 config matching 10_chat_plugins/config.yaml
    agent = V1AgentConfig(
        name="default",
        model="gpt-4o",
        system_prompt="You are a helpful assistant.",
        plugins=["WeatherPlugin"],
    )
    spec = V1Spec(agent=agent)
    config = BaseConfig(
        apiVersion="skagents/v1",
        service_name="WeatherBot",
        version="0.1",
        description="A weather chat agent",
        spec=spec,
    )

    # Create app with metadata route
    app = FastAPI()
    utility_routes = UtilityRoutes()
    app.include_router(
        utility_routes.get_metadata_routes(config=config),
        prefix="/WeatherBot/0.1",
    )

    # Call the endpoint
    client = TestClient(app)
    response = client.get("/WeatherBot/0.1/metadata")

    print(f"  HTTP Status: {response.status_code}")
    data = response.json()
    print_response(data)

    results = []
    results.append(check("Status code is 200", response.status_code == 200, response.status_code, 200))
    results.append(check("agent_name is 'WeatherBot'", data["agent_name"] == "WeatherBot", data["agent_name"], "WeatherBot"))
    results.append(check("description is 'A weather chat agent'", data["description"] == "A weather chat agent", data["description"], "A weather chat agent"))
    results.append(check("model is 'gpt-4o'", data["model"] == "gpt-4o", data["model"], "gpt-4o"))
    results.append(check("plugins contains 'WeatherPlugin'", data["plugins"] == ["WeatherPlugin"], data["plugins"], ["WeatherPlugin"]))
    return all(results)


def test_appv3_metadata():
    """Test /metadata endpoint for AppV3 (tealagents/v1alpha1) config."""
    print_header("TEST 2: AppV3 (tealagents/v1alpha1) - MathAgent with plugins")

    # Build a real V3 config matching 11_hitl/config.yaml
    agent = V3AgentConfig(
        name="default",
        model="gpt-4o-2024-05-13",
        system_prompt="Your task is to help with Math problems.",
        plugins=["sensitive_plugin"],
    )
    spec = V3Spec(agent=agent)
    config = BaseConfig(
        apiVersion="tealagents/v1alpha1",
        name="MathAgent",
        version="0.1",
        description="A math helper agent",
        spec=spec,
    )

    # Create app with metadata route
    app = FastAPI()
    utility_routes = UtilityRoutes()
    app.include_router(
        utility_routes.get_metadata_routes(config=config),
        prefix="/MathAgent/0.1",
    )

    # Call the endpoint
    client = TestClient(app)
    response = client.get("/MathAgent/0.1/metadata")

    print(f"  HTTP Status: {response.status_code}")
    data = response.json()
    print_response(data)

    results = []
    results.append(check("Status code is 200", response.status_code == 200, response.status_code, 200))
    results.append(check("agent_name is 'MathAgent'", data["agent_name"] == "MathAgent", data["agent_name"], "MathAgent"))
    results.append(check("description is 'A math helper agent'", data["description"] == "A math helper agent", data["description"], "A math helper agent"))
    results.append(check("model is 'gpt-4o-2024-05-13'", data["model"] == "gpt-4o-2024-05-13", data["model"], "gpt-4o-2024-05-13"))
    results.append(check("plugins contains 'sensitive_plugin'", data["plugins"] == ["sensitive_plugin"], data["plugins"], ["sensitive_plugin"]))
    return all(results)


def test_appv1_no_plugins():
    """Test /metadata for an agent with no plugins."""
    print_header("TEST 3: AppV1 - Simple ChatBot (no plugins)")

    agent = V1AgentConfig(
        name="default",
        model="gpt-4o-mini",
        system_prompt="You are a helpful assistant.",
    )
    spec = V1Spec(agent=agent)
    config = BaseConfig(
        apiVersion="skagents/v1",
        service_name="ChatBot",
        version="0.1",
        description="A simple chat agent",
        spec=spec,
    )

    app = FastAPI()
    utility_routes = UtilityRoutes()
    app.include_router(
        utility_routes.get_metadata_routes(config=config),
        prefix="/ChatBot/0.1",
    )

    client = TestClient(app)
    response = client.get("/ChatBot/0.1/metadata")

    print(f"  HTTP Status: {response.status_code}")
    data = response.json()
    print_response(data)

    results = []
    results.append(check("Status code is 200", response.status_code == 200))
    results.append(check("agent_name is 'ChatBot'", data["agent_name"] == "ChatBot"))
    results.append(check("model is 'gpt-4o-mini'", data["model"] == "gpt-4o-mini"))
    results.append(check("plugins is None (no plugins)", data["plugins"] is None, data["plugins"], None))
    return all(results)


def test_appv3_with_metadata_description():
    """Test that metadata.description takes precedence over top-level description."""
    print_header("TEST 4: AppV3 - Metadata description takes precedence")

    agent = V3AgentConfig(
        name="default",
        model="gpt-4",
        system_prompt="You are a helpful assistant.",
    )
    spec = V3Spec(agent=agent)
    config = BaseConfig(
        apiVersion="tealagents/v1alpha1",
        name="mcp-demo-agent",
        version="1.0",
        description="Top-level description (should NOT be used)",
        metadata=ConfigMetadata(
            description="A demonstration agent that showcases MCP integration",
            skills=[
                ConfigSkill(
                    id="mcp-tools",
                    name="MCP Tools",
                    description="Tools from MCP servers",
                    tags=["mcp"],
                )
            ],
        ),
        spec=spec,
    )

    app = FastAPI()
    utility_routes = UtilityRoutes()
    app.include_router(
        utility_routes.get_metadata_routes(config=config),
        prefix="/mcp-demo-agent/1.0",
    )

    client = TestClient(app)
    response = client.get("/mcp-demo-agent/1.0/metadata")

    print(f"  HTTP Status: {response.status_code}")
    data = response.json()
    print_response(data)

    results = []
    results.append(check("Status code is 200", response.status_code == 200))
    results.append(check(
        "description uses metadata.description (not top-level)",
        data["description"] == "A demonstration agent that showcases MCP integration",
        data["description"],
        "A demonstration agent that showcases MCP integration",
    ))
    return all(results)


def test_response_schema():
    """Test that the response JSON has exactly the expected fields."""
    print_header("TEST 5: Response schema validation")

    config = BaseConfig(
        apiVersion="skagents/v1",
        name="schema-test",
        version="1.0",
    )

    app = FastAPI()
    utility_routes = UtilityRoutes()
    app.include_router(utility_routes.get_metadata_routes(config=config))

    client = TestClient(app)
    response = client.get("/metadata")
    data = response.json()

    expected_fields = {"agent_name", "description", "model", "plugins"}
    actual_fields = set(data.keys())

    print(f"  Expected fields: {expected_fields}")
    print(f"  Actual fields:   {actual_fields}")

    results = []
    results.append(check("Response has exactly 4 expected fields", actual_fields == expected_fields, actual_fields, expected_fields))
    return all(results)


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  METADATA ENDPOINT MANUAL VALIDATION")
    print("  " + "=" * 56)
    print("  Testing /metadata endpoint for AppV1 and AppV3")
    print("=" * 60)

    all_passed = True
    all_passed &= test_appv1_metadata()
    all_passed &= test_appv3_metadata()
    all_passed &= test_appv1_no_plugins()
    all_passed &= test_appv3_with_metadata_description()
    all_passed &= test_response_schema()

    print_header("FINAL RESULT")
    if all_passed:
        print(f"  {PASS} ALL TESTS PASSED — Ticket is resolved!")
        print(f"\n  The /metadata endpoint correctly returns:")
        print(f"    • agent_name  — from config name/service_name")
        print(f"    • description — from metadata.description or top-level")
        print(f"    • model       — from spec.agent.model")
        print(f"    • plugins     — from spec.agent.plugins + remote_plugins + mcp_servers")
        sys.exit(0)
    else:
        print(f"  {FAIL} SOME TESTS FAILED — See above for details")
        sys.exit(1)
