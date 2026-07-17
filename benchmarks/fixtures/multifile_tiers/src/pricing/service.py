from src.pricing.tiers import unit_price


def line_total(quantity):
    return quantity * unit_price(quantity)
