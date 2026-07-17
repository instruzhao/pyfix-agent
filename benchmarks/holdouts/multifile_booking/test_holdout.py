from datetime import datetime, timedelta, timezone

from src.booking.api import overlaps


def test_contained_and_disjoint_intervals():
    start = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    assert overlaps(start, start + timedelta(hours=3), start + timedelta(hours=1), start + timedelta(hours=2))
    assert not overlaps(start, start + timedelta(hours=1), start + timedelta(hours=2), start + timedelta(hours=3))
