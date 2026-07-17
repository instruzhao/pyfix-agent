import pytest

from src.flags.api import flag_value


def test_false_string_override_is_preserved():
    assert flag_value(True, override="0") is False


def test_invalid_explicit_override_is_not_hidden_by_default():
    with pytest.raises(ValueError):
        flag_value(True, override="")
