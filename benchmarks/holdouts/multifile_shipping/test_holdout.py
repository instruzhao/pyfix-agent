from src.checkout.api import checkout_total


def test_zero_discount_and_below_threshold():
    assert checkout_total(119, 0, 120, 5) == 124


def test_discount_can_move_order_below_threshold():
    assert checkout_total(120, 1, 120, 5) == 124
