from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class LineItem:
    sku: str
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class OrderSummary:
    subtotal: Decimal
    discount: Decimal
    tax: Decimal
    shipping: Decimal
    total: Decimal


def calculate_order_total(
    items: list[LineItem],
    tax_rate: Decimal,
    discount_rate: Decimal = Decimal("0.00"),
    free_shipping_threshold: Decimal = Decimal("100.00"),
    shipping_fee: Decimal = Decimal("8.50"),
) -> OrderSummary:
    subtotal = sum(item.unit_price * item.quantity for item in items)
    discount = subtotal * discount_rate
    taxable_amount = subtotal
    tax = taxable_amount * tax_rate
    shipping = Decimal("0.00") if subtotal >= free_shipping_threshold else shipping_fee
    total = subtotal - discount + tax + shipping

    return OrderSummary(
        subtotal=subtotal,
        discount=discount,
        tax=tax,
        shipping=shipping,
        total=total,
    )
