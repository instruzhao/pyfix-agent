from src.billing.allocation import prorated_cents


def invoice_total(cents, active_days, days_in_period):
    return prorated_cents(cents, active_days, days_in_period)
