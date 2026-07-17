from src.flags.api import flag_value


def test_explicit_false_override_is_not_replaced_by_default():
    assert flag_value(True, override=False) is False


def test_none_uses_default():
    assert flag_value("yes", override=None) is True
