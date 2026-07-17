import pytest

from src.inventory.api import reserve


def test_over_reservation_is_rejected():
    with pytest.raises(ValueError, match="stock"):
        reserve(5, 6)


def test_negative_quantity_is_rejected():
    with pytest.raises(ValueError, match="quantity"):
        reserve(5, -1)
