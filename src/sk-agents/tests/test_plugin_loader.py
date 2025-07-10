from unittest.mock import MagicMock, patch

import pytest

from sk_agents.plugin_loader import PluginLoader, get_plugin_loader


def test_successful_plugin_loading():
    mock_plugin = MagicMock()
    mock_plugin.ExamplePlugin = object()

    with patch("sk_agents.plugin_loader.ModuleLoader.load_module", return_value=mock_plugin):
        loader = PluginLoader("mock_module")
        plugins = loader.get_plugins(["ExamplePlugin"])
        assert "ExamplePlugin" in plugins
        assert plugins["ExamplePlugin"] is mock_plugin.ExamplePlugin


def test_plugin_not_found():
    class EmptyPlugin:
        pass  # No attributes

    with patch("sk_agents.plugin_loader.ModuleLoader.load_module", return_value=EmptyPlugin()):
        loader = PluginLoader("mock_module")
        with pytest.raises(ValueError, match="Plugin MissingPlugin not found"):
            loader.get_plugins(["MissingPlugin"])


def test_invalid_module_path():
    with patch(
        "sk_agents.plugin_loader.ModuleLoader.load_module",
        side_effect=FileNotFoundError("Module not found"),
    ):
        with pytest.raises(ImportError, match="Cannot load plugin module 'bad_path'"):
            PluginLoader("bad_path")


def test_get_plugins_without_module():
    loader = PluginLoader(None)
    with pytest.raises(RuntimeError, match="Custom module not loaded"):
        loader.get_plugins(["Anything"])


def test_get_plugin_loader_singleton(monkeypatch):
    # Reset the singleton
    monkeypatch.setattr("sk_agents.plugin_loader._plugin_loader", None)

    mock_module = object()

    with patch("sk_agents.plugin_loader.ModuleLoader.load_module", return_value=mock_module):
        loader1 = get_plugin_loader("mod1")
        loader2 = get_plugin_loader("mod2")  # Should reuse same instance

        assert isinstance(loader1, PluginLoader)
        assert loader1 is loader2


@pytest.mark.parametrize(
    "input_path, expected",
    [
        ("some/path/plugin.py", "plugin"),
        ("plugin.py", "plugin"),
        ("plugin", "plugin"),
        ("some/dir.name/weird.plugin.name.py", "weird"),
        ("", ""),  # edge case: empty string
        ("/", ""),  # edge case: root path
    ],
)
def test_parse_module_name(input_path, expected):
    assert PluginLoader._parse_module_name(input_path) == expected
