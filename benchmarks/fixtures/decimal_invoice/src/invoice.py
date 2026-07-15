from decimal import Decimal


def invoice_totals(items, tax_rate):
    subtotal = sum(quantity * unit_price for quantity, unit_price in items)
    tax = subtotal * tax_rate
    return subtotal, tax, subtotal + tax
