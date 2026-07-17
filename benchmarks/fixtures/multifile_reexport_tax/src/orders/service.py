def calculate_total(subtotal, discount_rate, tax_rate):
    discount = subtotal * discount_rate
    tax = subtotal * tax_rate
    return subtotal - discount + tax
