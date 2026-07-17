from src.checkout.api import checkout_total


def test_shipping_threshold_uses_discounted_subtotal():
    assert checkout_total(130, 26, 120, 9.99) == 113.99


def test_fee_is_waived_at_discounted_threshold():
    assert checkout_total(130, 10, 120, 9.99) == 120
