from src.orders.service import calculate_total


def order_total(subtotal, discount_rate, tax_rate):
    return calculate_total(subtotal, discount_rate, tax_rate)
