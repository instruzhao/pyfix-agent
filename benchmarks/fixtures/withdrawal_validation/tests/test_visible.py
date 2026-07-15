import pytest

from src.account import withdraw


def test_rejects_negative_withdrawal():
    with pytest.raises(ValueError, match="positive"):
        withdraw(100, -10)
