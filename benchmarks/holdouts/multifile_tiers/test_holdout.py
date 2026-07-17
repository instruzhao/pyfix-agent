from src.pricing.api import price_for


def test_second_tier_boundary_and_open_ended_tier():
    assert price_for(50) == 450
    assert price_for(51) == 408


def test_smallest_valid_quantity():
    assert price_for(1) == 10
