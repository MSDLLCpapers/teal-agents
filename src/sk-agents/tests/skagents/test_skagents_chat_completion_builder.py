import os

import pytest
from ska_utils import AppConfig

from sk_agents.configs import configs
from sk_agents.skagents.chat_completion_builder import ChatCompletionBuilder


@pytest.fixture()
def setup_env_fixture():
    os.environ["TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE"] = (
        "tests/custom/mock_chat_completion_factory.py"
    )
    os.environ["TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME"] = "MockChatCompletionFactory"
    os.environ["TA_API_KEY"] = "SomeMockKey"


@pytest.fixture()
def app_config_fixture():
    AppConfig.add_configs(configs)
    app_config = AppConfig()
    return app_config


def test_init_with_no_module(setup_env_fixture, app_config_fixture):
    os.environ.pop("TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE", None)
    AppConfig.add_configs(configs)
    chat_completion_builder = ChatCompletionBuilder(app_config_fixture)
    assert isinstance(chat_completion_builder, ChatCompletionBuilder)


def test_init_with_custom_module(setup_env_fixture, app_config_fixture):
    chat_completion_builder = ChatCompletionBuilder(app_config_fixture)
    assert isinstance(chat_completion_builder, ChatCompletionBuilder)


def test_init_custom_chat_completion_class_not_found(setup_env_fixture, app_config_fixture):
    os.environ.pop("TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME", None)
    AppConfig.add_configs(configs)
    with pytest.raises(ValueError) as excinfo:
        ChatCompletionBuilder(app_config_fixture)
    assert str(excinfo.value) == "Custom Chat Completion Factory class name not provided"


def test_init_custom_chat_completion_invalid_class(setup_env_fixture, app_config_fixture):
    os.environ["TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME"] = "InvalidClassName"
    AppConfig.add_configs(configs)
    with pytest.raises(ValueError) as excinfo:
        ChatCompletionBuilder(app_config_fixture)
    assert (
        str(excinfo.value) == f"Custom Chat Completion Factory class: "
        f"{os.environ['TA_CUSTOM_CHAT_COMPLETION_FACTORY_CLASS_NAME']}"
        f"Not found in module: {os.environ['TA_CUSTOM_CHAT_COMPLETION_FACTORY_MODULE']}"
    )


def test_get_chat_completion_for_model(setup_env_fixture, app_config_fixture):
    chat_completion_builder = ChatCompletionBuilder(app_config_fixture)
    chat_completion = chat_completion_builder.get_chat_completion_for_model("test-id", "gpt-model")
    assert chat_completion == {"service_id": "test-id", "ai_model_id": "gpt-model"}


def test_get_chat_completion_for_model_error(setup_env_fixture, app_config_fixture):
    chat_completion_builder = ChatCompletionBuilder(app_config_fixture)
    with pytest.raises(ValueError):
        chat_completion_builder.get_chat_completion_for_model("test-id", "unsuppored-model")


def test_get_model_type_for_name(setup_env_fixture, app_config_fixture):
    chat_completion_builder = ChatCompletionBuilder(app_config_fixture)
    model_type = chat_completion_builder.get_model_type_for_name("gpt-model")
    assert model_type == "openai"


def test_get_model_type_for_name_error(setup_env_fixture, app_config_fixture):
    chat_completion_builder = ChatCompletionBuilder(app_config_fixture)
    with pytest.raises(ValueError):
        chat_completion_builder.get_model_type_for_name("unsupported-model")


def test_get_model_supports_structured_output(setup_env_fixture, app_config_fixture):
    chat_completion_builder = ChatCompletionBuilder(app_config_fixture)
    does_support = chat_completion_builder.model_supports_structured_output(model_name="gpt-model")
    assert does_support is True


def test_get_model_supports_structured_output_error(setup_env_fixture, app_config_fixture):
    chat_completion_builder = ChatCompletionBuilder(app_config_fixture)
    with pytest.raises(ValueError):
        chat_completion_builder.model_supports_structured_output("unsupported-model")
