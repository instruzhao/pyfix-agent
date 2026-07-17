from src.checkout.service import quote_order


def checkout_total(subtotal, discount, free_shipping_threshold, standard_fee):
    return quote_order(subtotal, discount, free_shipping_threshold, standard_fee)
