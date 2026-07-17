TIERS = ((10, 10), (50, 9), (None, 8))


def unit_price(quantity):
    for maximum, price in TIERS:
        if maximum is None or quantity < maximum:
            return price
    raise RuntimeError("unreachable")
