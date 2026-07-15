from src.service import order_total


def test_zero_discount_and_zero_tax():
    assert order_total(50.0, discount_rate=0.0, tax_rate=0.10) == 55.0
    assert order_total(50.0, discount_rate=0.25, tax_rate=0.0) == 37.5
