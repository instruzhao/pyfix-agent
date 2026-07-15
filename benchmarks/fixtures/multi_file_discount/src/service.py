from src.rules import discount_amount


def order_total(subtotal, discount_rate, tax_rate):
    discount = discount_amount(subtotal, discount_rate)
    tax = subtotal * tax_rate
    return subtotal - discount + tax
