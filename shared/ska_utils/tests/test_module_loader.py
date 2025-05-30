from unittest.mock import MagicMock, patch

import pytest

from ska_utils import ModuleLoader


def test_parse_module_name():
    # Test with file path
    result = ModuleLoader._parse_module_name("/path/to/module.py")
    assert result == "module"
    # Test with file name only
    result = ModuleLoader._parse_module_name("module.py")
    assert result == "module"
    # Test with path that has no extension
    result = ModuleLoader._parse_module_name("/path/to/module")
    assert result == "module"


def test_load_module_success():
    mock_spec = MagicMock()
    mock_spec.loader = MagicMock()
    mock_spec.loader.exec_module = MagicMock()
    with (
        patch(
            "importlib.util.spec_from_file_location", return_value=mock_spec
        ) as mock_spec_from_file_location,
        patch("importlib.util.module_from_spec", return_value=mock_spec) as mock_module_from_spec,
    ):
        module = ModuleLoader.load_module("/path/to/module.py")

        mock_module_from_spec.assert_called_once()
        mock_spec_from_file_location.assert_called_once()
        assert module is not None


def test_load_module_spec_is_none():
    with patch("importlib.util.spec_from_file_location", return_value=None):
        with pytest.raises(ImportError, match="spec is None. Unable to load the module."):
            ModuleLoader.load_module("/path/to/module.py")


def test_load_module_loader_is_none():
    mock_spec = MagicMock()
    mock_spec.loader = None

    with (
        patch("importlib.util.spec_from_file_location", return_value=mock_spec),
        patch("importlib.util.module_from_spec", return_value=mock_spec),
    ):
        with pytest.raises(
            ImportError, match="Module spec.loader is None. Unable to load the module."
        ):
            ModuleLoader.load_module("/path/to/module.py")
