from datetime import datetime, timedelta, timezone

from src.calendar.api import conflicts


def test_contained_and_disjoint_bookings_keep_half_open_semantics():
    start = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    assert conflicts(start, start + timedelta(hours=3), start + timedelta(hours=1), start + timedelta(hours=2))
    assert not conflicts(start, start + timedelta(hours=1), start + timedelta(hours=2), start + timedelta(hours=3))
