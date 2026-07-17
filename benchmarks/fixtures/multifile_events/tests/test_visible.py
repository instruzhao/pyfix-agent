import pytest

from src.events.api import unique_events


def test_first_event_for_an_id_wins_and_order_is_preserved():
    events = [
        {"id": "a", "value": 1},
        {"id": "b", "value": 2},
        {"id": "a", "value": 99},
    ]
    assert unique_events(events) == events[:2]


def test_missing_identity_is_rejected():
    with pytest.raises(ValueError, match="id"):
        unique_events([{"value": 1}])
