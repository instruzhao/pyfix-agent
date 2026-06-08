from decimal import Decimal

import pytest

from src.billing import LineItem, calculate_order_total


def test_calculate_order_total_applies_discount_before_tax_and_rounds_money():
    items = [
        LineItem(sku="keyboard", quantity=2, unit_price=Decimal("49.995")),
        LineItem(sku="cable", quantity=1, unit_price=Decimal("12.335")),
    ]

    summary = calculate_order_total(
        items=items,
        tax_rate=Decimal("0.0825"),
        discount_rate=Decimal("0.10"),
        free_shipping_threshold=Decimal("120.00"),
        shipping_fee=Decimal("8.50"),
    )

    assert summary.subtotal == Decimal("112.33")
    assert summary.discount == Decimal("11.23")
    assert summary.tax == Decimal("8.34")
    assert summary.shipping == Decimal("8.50")
    assert summary.total == Decimal("117.94")


def test_calculate_order_total_uses_free_shipping_after_discounted_order_value():
    items = [
        LineItem(sku="monitor", quantity=1, unit_price=Decimal("130.00")),
    ]

    summary = calculate_order_total(
        items=items,
        tax_rate=Decimal("0.05"),
        discount_rate=Decimal("0.20"),
        free_shipping_threshold=Decimal("120.00"),
        shipping_fee=Decimal("9.99"),
    )

    assert summary.subtotal == Decimal("130.00")
    assert summary.discount == Decimal("26.00")
    assert summary.tax == Decimal("5.20")
    assert summary.shipping == Decimal("9.99")
    assert summary.total == Decimal("119.19")


def test_calculate_order_total_rejects_invalid_line_items():
    with pytest.raises(ValueError, match="quantity"):
        calculate_order_total(
            items=[LineItem(sku="bad-quantity", quantity=0, unit_price=Decimal("10.00"))],
            tax_rate=Decimal("0.05"),
        )

    with pytest.raises(ValueError, match="unit_price"):
        calculate_order_total(
            items=[LineItem(sku="bad-price", quantity=1, unit_price=Decimal("-1.00"))],
            tax_rate=Decimal("0.05"),
        )
