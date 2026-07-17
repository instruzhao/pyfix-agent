from src.orders import order_total


def test_fractional_rates_follow_same_order():
    assert order_total(250, 0.15, 0.08) == 229.5


def test_full_discount_has_no_taxable_amount():
    assert order_total(50, 1, 0.20) == 0
