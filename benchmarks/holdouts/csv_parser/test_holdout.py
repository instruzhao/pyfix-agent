from src.records import parse_record


def test_parses_plain_and_escaped_quote_fields():
    assert parse_record("Ada,London") == {"name": "Ada", "city": "London"}
    assert parse_record('"Li ""Leo""",Beijing') == {"name": 'Li "Leo"', "city": "Beijing"}
