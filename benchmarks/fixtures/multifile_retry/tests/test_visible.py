import pytest

from src.retry.api import next_delay


def test_first_attempt_uses_base_delay_and_growth_is_capped():
    assert next_delay(1, 2, 10) == 2
    assert next_delay(5, 2, 10) == 10


def test_attempt_numbers_start_at_one():
    with pytest.raises(ValueError, match="attempt"):
        next_delay(0, 2, 10)
