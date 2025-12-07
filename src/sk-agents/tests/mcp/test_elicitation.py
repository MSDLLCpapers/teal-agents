import asyncio
import types
import pytest

from sk_agents.mcp_client import (
    ElicitationRequest,
    ElicitationResponse,
    _make_elicitation_error_handler,
    _make_elicitation_notification_handler,
    _register_elicitation_handler,
)
from sk_agents.mcp_plugin_registry import McpPluginRegistry
from sk_agents.mcp_client import McpTool, McpPlugin


class DummySession:
    def __init__(self):
        self.notifications = {}
        self.error_handler = None

    def add_notification_handler(self, name, fn):
        self.notifications[name] = fn

    def set_error_handler(self, fn):
        self.error_handler = fn


async def _noop_handler(req: ElicitationRequest) -> ElicitationResponse:
    return ElicitationResponse(action="accept", content={"ok": True})


def test_initialize_capability_advertised_via_handler_registration():
    # Ensure registration attaches handlers without throwing
    session = DummySession()
    _register_elicitation_handler(session, _noop_handler)
    assert "elicitation/create" in session.notifications
    assert "notifications/elicitation/complete" in session.notifications
    assert session.error_handler is not None


@pytest.mark.asyncio
async def test_notification_handler_invokes_callback_form():
    called = {}

    async def handler(req: ElicitationRequest) -> ElicitationResponse:
        called["req"] = req
        return ElicitationResponse(action="accept", content={"field": "val"})

    fn = _make_elicitation_notification_handler(handler)
    resp = await fn(
        {
            "mode": "form",
            "message": "Need input",
            "requestedSchema": {"type": "object"},
            "elicitationId": "eid-1",
            "url": None,
            "server": "s1",
        }
    )

    req = called["req"]
    assert req.mode == "form"
    assert req.message == "Need input"
    assert req.requested_schema == {"type": "object"}
    assert req.elicitation_id == "eid-1"
    assert resp == {"result": {"action": "accept", "content": {"field": "val"}}}


@pytest.mark.asyncio
async def test_notification_handler_rejects_on_exception():
    async def handler(_):
        raise RuntimeError("boom")

    fn = _make_elicitation_notification_handler(handler)
    resp = await fn({"mode": "form", "message": "x"})
    assert resp == {"result": {"action": "reject", "content": None}}


@pytest.mark.asyncio
async def test_error_handler_url_mode_calls_handler_per_item():
    seen = []

    async def handler(req: ElicitationRequest):
        seen.append(req)
        return ElicitationResponse(action="accept", content=None)

    fn = _make_elicitation_error_handler(handler)
    await fn(
        {
            "code": -32042,
            "data": {
                "elicitations": [
                    {"mode": "url", "message": "go", "url": "https://x", "elicitationId": "a", "server": "s1"},
                    {"mode": "url", "message": "go2", "url": "https://y", "elicitationId": "b", "server": "s2"},
                ]
            },
        }
    )

    assert len(seen) == 2
    assert seen[0].url == "https://x"
    assert seen[1].elicitation_id == "b"


@pytest.mark.asyncio
async def test_dynamic_plugin_receives_elicitation_handler():
    # Build plugin class
    tools = [McpTool("t", "desc", {}, None, server_config=types.SimpleNamespace(model_dump=lambda: {}), server_name="srv")]
    plugin_cls = McpPluginRegistry._create_plugin_class(tools, "srv")

    captured = {}

    async def handler(req: ElicitationRequest) -> ElicitationResponse:
        captured["req"] = req
        return ElicitationResponse(action="accept", content=None)

    # Patch McpTool.invoke to record the handler
    async def fake_invoke(self, user_id, session_id=None, discovery_manager=None, app_config=None, elicitation_handler=None, **kwargs):
        captured["handler"] = elicitation_handler
        return "ok"

    orig_invoke = McpTool.invoke
    McpTool.invoke = fake_invoke  # type: ignore

    try:
        plugin = plugin_cls(
            user_id="u",
            authorization=None,
            extra_data_collector=None,
            session_id="s",
            discovery_manager=None,
            app_config=None,
            elicitation_handler=handler,
        )

        # Call generated function (attribute name sanitized)
        func = getattr(plugin, "srv_t")
        await func()

        assert captured.get("handler") is handler
    finally:
        McpTool.invoke = orig_invoke

