from src.config import parse_bool


def test_boolean_strings_are_case_insensitive():
    assert parse_bool("YES") is True
    assert parse_bool("0") is False
    assert parse_bool(False) is False
