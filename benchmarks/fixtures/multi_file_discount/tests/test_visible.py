from src.service import order_total


def test_tax_is_applied_after_discount():
    assert order_total(100.0, discount_rate=0.20, tax_rate=0.10) == 88.0
