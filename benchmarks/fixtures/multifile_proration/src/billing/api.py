from src.billing.service import invoice_total


def total(cents, active_days, days_in_period):
    return invoice_total(cents, active_days, days_in_period)
