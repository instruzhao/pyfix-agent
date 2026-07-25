from src.billing.api import total


def test_proration_uses_bankers_rounding_for_financial_ties():
    assert total(1, 1, 2) == 0
    assert total(3, 1, 2) == 2


def test_full_period_returns_the_original_amount():
    assert total(1099, 30, 30) == 1099
