from decimal import Decimal

from src.invoice import invoice_totals


def test_half_cent_subtotal_rounds_up():
    assert invoice_totals([(3, Decimal("0.335"))], Decimal("0.00")) == (
        Decimal("1.01"), Decimal("0.00"), Decimal("1.01")
    )
