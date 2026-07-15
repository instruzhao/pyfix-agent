from src.config import parse_bool


def test_common_boolean_strings():
    assert parse_bool("true") is True
    assert parse_bool("false") is False
    assert parse_bool("no") is False
