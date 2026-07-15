from datetime import date

from src.dates import inclusive_dates


def test_single_day_range():
    day = date(2026, 2, 4)
    assert inclusive_dates(day, day) == [day]
