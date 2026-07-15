import pytest

from src.account import withdraw


def test_valid_and_insufficient_withdrawals():
    assert withdraw(100, 40) == 60
    with pytest.raises(ValueError, match="insufficient"):
        withdraw(10, 11)
