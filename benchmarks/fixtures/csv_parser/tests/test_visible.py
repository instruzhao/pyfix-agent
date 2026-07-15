from src.records import parse_record


def test_parses_quoted_csv_field():
    assert parse_record('"Doe, Jane",Shanghai') == {"name": "Doe, Jane", "city": "Shanghai"}
