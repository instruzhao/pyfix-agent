from src.checkout.policy import shipping_fee


def quote_order(subtotal, discount, free_shipping_threshold, standard_fee):
    discounted_subtotal = subtotal - discount
    fee = shipping_fee(subtotal, discount, free_shipping_threshold, standard_fee)
    return discounted_subtotal + fee
