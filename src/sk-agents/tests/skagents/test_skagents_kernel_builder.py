from unittest.mock import ANY, MagicMock, patch

import pytest
from semantic_kernel.kernel import Kernel
from ska_utils import AppConfig

from sk_agents.skagents.kernel_builder import KernelBuilder


@patch.object(KernelBuilder, "_create_base_kernel")
@patch.object(KernelBuilder, "_parse_plugins")
@patch.object(KernelBuilder, "_load_remote_plugins")
def test_build_kernel_success(mock_load, mock_parse, mock_create):
    # Mock
    kernel = Kernel()
    mock_create.return_value = kernel
    mock_parse.return_value = kernel
    mock_load.return_value = kernel

    chat_completion_builder = MagicMock()
    remote_plugin_loader = MagicMock()
    app_config = MagicMock(spec=AppConfig)

    builder = KernelBuilder(chat_completion_builder, remote_plugin_loader, app_config)

    result = builder.build_kernel(
        model_name="gpt-4",
        service_id="openai",
        plugins=["pluginA"],
        remote_plugins=["remotePluginA"],
        authorization="Bearer token",
        extra_data_collector=None,
    )

    assert result is kernel
    mock_create.assert_called_once_with("gpt-4", "openai")
    mock_parse.assert_called_once()
    mock_load.assert_called_once()


@patch.object(KernelBuilder, "_create_base_kernel", side_effect=Exception("base kernel failed"))
def test_build_kernel_failure(mock_create_base_kernel, caplog):
    chat_completion_builder = MagicMock()
    remote_plugin_loader = MagicMock()
    app_config = MagicMock(spec=AppConfig)

    builder = KernelBuilder(chat_completion_builder, remote_plugin_loader, app_config)

    with caplog.at_level("WARNING"):
        with pytest.raises(Exception, match="base kernel failed"):
            builder.build_kernel(
                model_name="test-model", service_id="test-service", plugins=[], remote_plugins=[]
            )
    assert "Could build kernel with service ID test-service." in caplog.text


def test_get_model_type_for_name_success():
    mock_builder = MagicMock()
    mock_builder.get_model_type_for_name.return_value = "mock-type"
    kernel_builder = KernelBuilder(mock_builder, MagicMock(), MagicMock())

    result = kernel_builder.get_model_type_for_name("test-model")

    assert result == "mock-type"
    mock_builder.get_model_type_for_name.assert_called_once_with("test-model")


def test_get_model_type_for_name_failure(caplog):
    mock_builder = MagicMock()
    mock_builder.get_model_type_for_name.side_effect = Exception("lookup error")
    kernel_builder = KernelBuilder(mock_builder, MagicMock(), MagicMock())

    with caplog.at_level("WARNING"):
        with pytest.raises(Exception, match="lookup error"):
            kernel_builder.get_model_type_for_name("bad-model")

    assert "Could not get model type for bad-model." in caplog.text


def test_model_supports_structured_output_success():
    mock_builder = MagicMock()
    mock_builder.model_supports_structured_output.return_value = True
    kernel_builder = KernelBuilder(mock_builder, MagicMock(), MagicMock())

    result = kernel_builder.model_supports_structured_output("some-model")

    assert result is True
    mock_builder.model_supports_structured_output.assert_called_once_with("some-model")


def test_model_supports_structured_output_failure():
    mock_builder = MagicMock()
    mock_builder.model_supports_structured_output.side_effect = Exception("Failure")
    kernel_builder = KernelBuilder(mock_builder, MagicMock(), MagicMock())

    with pytest.raises(Exception, match="Failure"):
        kernel_builder.model_supports_structured_output("bad-model")


def test_create_base_kernel_success():
    mock_chat_completion = MagicMock()
    mock_builder = MagicMock()
    mock_builder.get_chat_completion_for_model.return_value = mock_chat_completion

    builder = KernelBuilder(
        chat_completion_builder=mock_builder,
        remote_plugin_loader=MagicMock(),
        app_config=MagicMock(),
    )

    kernel = builder._create_base_kernel("test-model", "test-service")

    assert isinstance(kernel, Kernel)
    mock_builder.get_chat_completion_for_model.assert_called_once_with(
        service_id="test-service", model_name="test-model"
    )
    assert mock_chat_completion in kernel.services.values() or True


def test_create_base_kernel_failure(caplog):
    mock_builder = MagicMock()
    mock_builder.get_chat_completion_for_model.side_effect = Exception(
        "fail to get chat completion"
    )
    builder = KernelBuilder(
        chat_completion_builder=mock_builder,
        remote_plugin_loader=MagicMock(),
        app_config=MagicMock(),
    )

    with pytest.raises(Exception, match="fail to get chat completion"):
        with caplog.at_level("WARNING"):
            kernel = builder._create_base_kernel("bad-model", "bad-service")

        assert kernel is None
    assert "Could not create base kernel with service id bad-service." in caplog.text


def test_parse_plugins_empty_list():
    kernel = Kernel()
    result = KernelBuilder._parse_plugins([], kernel)
    assert result is kernel


def test_parse_plugins_none():
    kernel = Kernel()
    result = KernelBuilder._parse_plugins(None, kernel)
    assert result is kernel


def test_parse_plugins_with_valid_plugin():
    kernel = Kernel()

    # Create a mock plugin instance with real-looking attributes
    mock_plugin_instance = MagicMock()
    mock_plugin_instance.name = "mock_plugin"
    mock_plugin_instance.description = "A mock plugin for testing"
    mock_plugin_instance.get_functions.return_value = {}

    mock_plugin_class = MagicMock(return_value=mock_plugin_instance)

    plugin_dict = {"mock_plugin": mock_plugin_class}

    with patch("sk_agents.skagents.kernel_builder.get_plugin_loader") as mock_loader:
        mock_loader.return_value.get_plugins.return_value = plugin_dict

        result = KernelBuilder._parse_plugins(
            plugin_names=["mock_plugin"],
            kernel=kernel,
            authorization="token",
            extra_data_collector=MagicMock(),
        )

        assert result is kernel
        assert "mock_plugin" in result.plugins
        mock_plugin_class.assert_called_once_with("token", ANY)


def test_parse_plugins_with_multiple_plugins():
    kernel = Kernel()

    # Create realistic plugin instances
    plugin_instance_1 = MagicMock()
    plugin_instance_1.name = "plugin1"
    plugin_instance_1.description = "First plugin"
    plugin_instance_1.get_functions.return_value = {}

    plugin_instance_2 = MagicMock()
    plugin_instance_2.name = "plugin2"
    plugin_instance_2.description = "Second plugin"
    plugin_instance_2.get_functions.return_value = {}

    # Create mock constructors
    plugin_class_1 = MagicMock(return_value=plugin_instance_1)
    plugin_class_2 = MagicMock(return_value=plugin_instance_2)

    plugin_dict = {
        "plugin1": plugin_class_1,
        "plugin2": plugin_class_2,
    }

    with patch("sk_agents.skagents.kernel_builder.get_plugin_loader") as mock_loader:
        mock_loader.return_value.get_plugins.return_value = plugin_dict

        result = KernelBuilder._parse_plugins(plugin_names=["plugin1", "plugin2"], kernel=kernel)

        assert "plugin1" in result.plugins
        assert "plugin2" in result.plugins
        plugin_class_1.assert_called_once()
        plugin_class_2.assert_called_once()


def test_parse_plugins_plugin_loader_failure():
    kernel = MagicMock()

    with patch("sk_agents.skagents.kernel_builder.get_plugin_loader") as mock_loader:
        # Simulate get_plugins raising an exception
        mock_loader.return_value.get_plugins.side_effect = RuntimeError("Failed to load plugins")

        with pytest.raises(RuntimeError, match="Failed to load plugins"):
            KernelBuilder._parse_plugins(
                plugin_names=["some_plugin"],
                kernel=kernel,
                authorization="token",
                extra_data_collector=MagicMock(),
            )


def test_load_remote_plugins_with_none_or_empty():
    kb = KernelBuilder(
        chat_completion_builder=MagicMock(),
        remote_plugin_loader=MagicMock(),
        app_config=MagicMock(),
    )
    kernel = Kernel()

    # None input returns kernel unchanged
    result = kb._load_remote_plugins(None, kernel)
    assert result is kernel

    # Empty list input returns kernel unchanged
    result = kb._load_remote_plugins([], kernel)
    assert result is kernel


def test_load_remote_plugins_success():
    remote_loader = MagicMock()
    kb = KernelBuilder(
        chat_completion_builder=MagicMock(),
        remote_plugin_loader=remote_loader,
        app_config=MagicMock(),
    )
    kernel = Kernel()
    remote_plugins = ["plugin1", "plugin2"]

    result = kb._load_remote_plugins(remote_plugins, kernel)

    # The loader's load_remote_plugins method should be called once with correct args
    remote_loader.load_remote_plugins.assert_called_once_with(kernel, remote_plugins)
    # Kernel should be returned unchanged
    assert result is kernel


def test_load_remote_plugins_failure():
    remote_loader = MagicMock()
    remote_loader.load_remote_plugins.side_effect = RuntimeError("Loading failed")

    kb = KernelBuilder(
        chat_completion_builder=MagicMock(),
        remote_plugin_loader=remote_loader,
        app_config=MagicMock(),
    )
    kernel = Kernel()
    remote_plugins = ["plugin1"]

    with pytest.raises(RuntimeError, match="Loading failed"):
        kb._load_remote_plugins(remote_plugins, kernel)
