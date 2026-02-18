from unittest.mock import MagicMock, patch

import pytest

from sk_agents.authorization.authorizer_factory import AuthorizerFactory
from sk_agents.authorization.dummy_authorizer import DummyAuthorizer
from sk_agents.configs import TA_AUTHORIZER_CLASS, TA_AUTHORIZER_MODULE


# Clears the Singleton cache before each test.
@pytest.fixture(autouse=True)
def reset_singleton():
    # Reset Singleton before each test
    AuthorizerFactory._instances = {}
    yield
    AuthorizerFactory._instances = {}


@pytest.fixture
def mock_app_config():
    return MagicMock()


@pytest.mark.asyncio
@patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
async def test_successful_initialization_and_get_authorizer(mock_load_module, mock_app_config):
    mock_app_config.get.side_effect = lambda key: {
        TA_AUTHORIZER_MODULE.env_name: "dummy_module",
        TA_AUTHORIZER_CLASS.env_name: "DummyAuthorizer",
    }.get(key)

    dummy_module = MagicMock()
    dummy_module.DummyAuthorizer = DummyAuthorizer
    # setattr(dummy_module, "DummyAuthorizer", DummyAuthorizer)
    mock_load_module.return_value = dummy_module

    factory = AuthorizerFactory(mock_app_config)
    authorizer = factory.get_authorizer()
    authorizer_response = await authorizer.authorize_request("Bearer xyz")
    assert isinstance(authorizer, DummyAuthorizer)
    assert authorizer_response == "dummyuser"


@patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
def test_module_load_failure_raises_import_error(mock_load_module, mock_app_config):
    mock_app_config.get.side_effect = lambda key: {
        TA_AUTHORIZER_MODULE.env_name: "nonexistent_module",
        TA_AUTHORIZER_CLASS.env_name: "SomeClass",
    }.get(key)

    mock_load_module.side_effect = Exception("Boom!")

    with pytest.raises(ImportError, match="Failed to load module 'nonexistent_module': Boom!"):
        AuthorizerFactory(mock_app_config)


@patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
def test_class_not_found_in_module_raises_import_error(mock_load_module, mock_app_config):
    mock_app_config.get.side_effect = lambda key: {
        TA_AUTHORIZER_MODULE.env_name: "some_module",
        TA_AUTHORIZER_CLASS.env_name: "MissingClass",
    }.get(key)

    class DummyModule:
        def __getattr__(self, item):
            raise AttributeError(f"No attribute '{item}'")

    mock_load_module.return_value = DummyModule()

    with pytest.raises(ImportError, match="Class 'MissingClass' not found"):
        AuthorizerFactory(mock_app_config)


@patch("sk_agents.authorization.authorizer_factory.ModuleLoader.load_module")
def test_class_not_subclass_of_request_authorizer_raises_type_error(
    mock_load_module, mock_app_config
):  # noqa: E501
    class InvalidAuthorizer:
        pass

    mock_app_config.get.side_effect = lambda key: {
        TA_AUTHORIZER_MODULE.env_name: "some_module",
        TA_AUTHORIZER_CLASS.env_name: "InvalidAuthorizer",
    }.get(key)

    dummy_module = MagicMock()
    dummy_module.InvalidAuthorizer = InvalidAuthorizer
    mock_load_module.return_value = dummy_module

    with pytest.raises(TypeError, match="is not a subclass of RequestAuthorizer"):
        AuthorizerFactory(mock_app_config)


def test_missing_module_env_variable_raises_value_error(mock_app_config):
    mock_app_config.get.side_effect = lambda key: (
        None if key == TA_AUTHORIZER_MODULE.env_name else "SomeClass"
    )  # noqa: E501

    with pytest.raises(ValueError, match="TA_AUTHORIZER_MODULE is not set"):
        AuthorizerFactory(mock_app_config)


def test_missing_class_env_variable_raises_value_error(mock_app_config):
    mock_app_config.get.side_effect = lambda key: (
        "some.module" if key == TA_AUTHORIZER_MODULE.env_name else None
    )  # noqa: E501

    with pytest.raises(ValueError, match="TA_AUTHORIZER_CLASS is not set"):
        AuthorizerFactory(mock_app_config)
