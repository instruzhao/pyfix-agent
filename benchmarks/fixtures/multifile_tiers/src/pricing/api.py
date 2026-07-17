from src.pricing.service import line_total


def price_for(quantity):
    return line_total(quantity)
