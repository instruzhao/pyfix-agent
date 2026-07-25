from decimal import Decimal, ROUND_UP


def prorated_cents(cents, active_days, days_in_period):
    if not 0 <= active_days <= days_in_period:
        raise ValueError("active_days")
    if days_in_period <= 0:
        raise ValueError("days_in_period")
    amount = Decimal(cents) * Decimal(active_days) / Decimal(days_in_period)
    return int(amount.quantize(Decimal("1"), rounding=ROUND_UP))
