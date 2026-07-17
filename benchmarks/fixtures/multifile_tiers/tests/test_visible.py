import pytest

from src.pricing.api import price_for


def test_tier_maximum_is_inclusive():
    assert price_for(10) == 100
    assert price_for(11) == 99


def test_quantity_must_be_positive():
    with pytest.raises(ValueError, match="quantity"):
        price_for(0)
