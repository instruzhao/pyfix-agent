def remaining_stock(current, quantity):
    if quantity >= current:
        raise ValueError("insufficient stock")
    return current - quantity
