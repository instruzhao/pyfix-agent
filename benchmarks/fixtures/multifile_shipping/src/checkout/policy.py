def shipping_fee(subtotal, discount, free_shipping_threshold, standard_fee):
    return 0 if subtotal >= free_shipping_threshold else standard_fee
