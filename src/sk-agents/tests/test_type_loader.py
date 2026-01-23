from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from sk_agents.ska_types import (
    BaseEmbeddedImage,
    BaseInput,
    BaseInputWithUserContext,
    BaseMultiModalInput,
    BaseMultiModalInputWithUserContext,
)
from sk_agents.type_loader import TypeLoader, get_type_loader


@pytest.mark.parametrize(
    "type_name,expected_type",
    [
        ("BaseInput", BaseInput),
        ("BaseInputWithUserContext", BaseInputWithUserContext),
        ("BaseMultiModalInput", BaseMultiModalInput),
        ("BaseMultiModalInputWithUserContext", BaseMultiModalInputWithUserContext),
        ("BaseEmbeddedImage", BaseEmbeddedImage),
    ],
)
def test_get_standard_type(type_name, expected_type):
    loader = TypeLoader()
    assert loader.get_type(type_name) == expected_type


@patch("sk_agents.type_loader.ModuleLoader.load_module")
def test_get_type_not_found_with_custom_module(mock_loader):
    mock_module = MagicMock()
    del mock_module.UnknownType  # Ensure attribute doesn't exist
    mock_loader.return_value = mock_module

    loader = TypeLoader("some_module.py")
    with pytest.raises(ValueError, match="Output type UnknownType not found"):
        loader.get_type("UnknownType")


def test_get_type_with_no_custom_module():
    loader = TypeLoader()  # No module passed, so custom_module will be None
    result = loader.get_type("CustomTypeThatDoesNotExist")
    assert result is None


def test_get_type_returns_cached_base_type():
    class CachedType(BaseModel):
        pass

    loader = TypeLoader()
    loader.custom_module = object()  # set any non-None value to bypass early return
    loader.base_types["CachedType"] = CachedType

    # Call get_type for a type_name already cached
    result = loader.get_type("CachedType")

    assert result is CachedType


def test_parse_module_name_valid():
    assert TypeLoader._parse_module_name("/some/path/module_name.py") == "module_name"


def test_parse_module_name_raises_on_none():
    with pytest.raises(AttributeError):
        TypeLoader._parse_module_name(None)


def test_parse_module_name_invalid_type():
    with pytest.raises(AttributeError):
        TypeLoader._parse_module_name(123)


@patch("sk_agents.type_loader.ModuleLoader.load_module")
def test_set_types_module_success(mock_loader):
    mock_module = MagicMock()
    mock_loader.return_value = mock_module
    loader = TypeLoader()
    loader.set_types_module("some_module.py")
    assert loader.custom_module == mock_module


@patch("sk_agents.type_loader.ModuleLoader.load_module", side_effect=ImportError("Failed"))
def test_set_types_module_failure(mock_loader):
    loader = TypeLoader()
    loader.set_types_module("bad_module.py")
    assert loader.custom_module is None


@patch("sk_agents.type_loader.ModuleLoader.load_module")
def test_get_custom_type(mock_loader):
    mock_type = MagicMock()
    mock_module = MagicMock()
    mock_module.CustomType = mock_type  # cleaner and equivalent to setattr
    mock_loader.return_value = mock_module

    loader = TypeLoader("some_module.py")
    assert loader.get_type("CustomType") == mock_type
    assert loader.base_types["CustomType"] == mock_type


def test_get_type_loader_singleton():
    loader1 = get_type_loader()
    loader2 = get_type_loader()
    assert loader1 is loader2
