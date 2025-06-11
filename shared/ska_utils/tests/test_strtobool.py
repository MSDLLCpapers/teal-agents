import pytest

from ska_utils import strtobool


def test_strtobool_true_values():
    assert strtobool("y") is True
    assert strtobool("yes") is True
    assert strtobool("t") is True
    assert strtobool("true") is True
    assert strtobool("on") is True
    assert strtobool("1") is True


def test_strtobool_false_values():
    assert strtobool("n") is False
    assert strtobool("no") is False
    assert strtobool("f") is False
    assert strtobool("false") is False
    assert strtobool("off") is False
    assert strtobool("0") is False


def test_strtobool_invalid_values():
    invalid_values = ["maybe", "yesno", "truefalse", "", " ", "123"]
    for value in invalid_values:
        with pytest.raises(ValueError, match=f"Invalid truth value: {value}"):
            strtobool(value)
