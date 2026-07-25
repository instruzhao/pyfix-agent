from src.billing.api import total


def test_proration_preserves_whole_cent_rounding():
    assert total(1000, 1, 3) == 333


def test_proration_rejects_more_active_days_than_period():
    try:
        total(1000, 31, 30)
    except ValueError:
        pass
    else:
        raise AssertionError("invalid period must be rejected")
