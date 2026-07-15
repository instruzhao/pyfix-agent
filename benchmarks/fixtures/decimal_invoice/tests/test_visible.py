from decimal import Decimal

from src.invoice import invoice_totals


def test_invoice_money_is_rounded_to_cents():
    assert invoice_totals([(2, Decimal("10.005"))], Decimal("0.10")) == (
        Decimal("20.01"), Decimal("2.00"), Decimal("22.01")
    )
