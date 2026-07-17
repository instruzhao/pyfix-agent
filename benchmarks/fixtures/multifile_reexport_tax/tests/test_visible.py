from src.orders import order_total


def test_tax_is_calculated_after_discount():
    assert order_total(100, 0.20, 0.10) == 88


def test_zero_tax_or_discount():
    assert order_total(100, 0, 0.10) == 110
    assert order_total(100, 0.20, 0) == 80
