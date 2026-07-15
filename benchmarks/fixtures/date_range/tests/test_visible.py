from datetime import date

from src.dates import inclusive_dates


def test_range_includes_both_endpoints():
    assert inclusive_dates(date(2026, 1, 1), date(2026, 1, 3)) == [
        date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 3)
    ]
