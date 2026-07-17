from src.events.api import unique_events


def test_equal_payloads_with_different_ids_are_distinct():
    events = [{"id": "a", "value": 1}, {"id": "b", "value": 1}]
    assert unique_events(events) == events


def test_empty_input_is_supported():
    assert unique_events([]) == []
