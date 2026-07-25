from datetime import datetime, timedelta, timezone

from src.calendar.api import conflicts


def test_adjacent_aware_bookings_do_not_conflict():
    start = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
    middle = start + timedelta(hours=1)
    assert conflicts(start, middle, middle, middle + timedelta(hours=1)) is False


def test_zero_length_booking_is_rejected():
    point = datetime(2026, 1, 1, tzinfo=timezone.utc)
    try:
        conflicts(point, point, point, point + timedelta(hours=1))
    except ValueError:
        pass
    else:
        raise AssertionError("zero-length booking must be rejected")
