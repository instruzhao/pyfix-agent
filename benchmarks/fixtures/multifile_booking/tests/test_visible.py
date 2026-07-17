from datetime import datetime, timedelta, timezone

import pytest

from src.booking.api import overlaps


def test_adjacent_half_open_bookings_do_not_overlap():
    start = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    middle = start + timedelta(hours=1)
    end = middle + timedelta(hours=1)
    assert overlaps(start, middle, middle, end) is False


def test_interval_end_must_follow_start():
    point = datetime(2026, 1, 1, tzinfo=timezone.utc)
    with pytest.raises(ValueError, match="end"):
        overlaps(point, point, point, point + timedelta(hours=1))
