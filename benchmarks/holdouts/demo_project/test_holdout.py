from decimal import Decimal

import pytest

from src.billing import LineItem, calculate_order_total


def test_rejects_negative_unit_price():
    with pytest.raises(ValueError, match="unit_price"):
        calculate_order_total([LineItem("bad", 1, Decimal("-0.01"))], Decimal("0.10"))


def test_shipping_uses_discounted_value():
    summary = calculate_order_total(
        [LineItem("item", 1, Decimal("100.00"))],
        tax_rate=Decimal("0.10"),
        discount_rate=Decimal("0.20"),
        free_shipping_threshold=Decimal("90.00"),
        shipping_fee=Decimal("5.00"),
    )
    assert summary.shipping == Decimal("5.00")
    assert summary.total == Decimal("93.00")
