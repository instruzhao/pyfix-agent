import pytest

from src.inventory.api import reserve


def test_reserving_all_available_stock_is_allowed():
    assert reserve(5, 5) == 0


def test_quantity_must_be_positive():
    with pytest.raises(ValueError, match="quantity"):
        reserve(5, 0)
