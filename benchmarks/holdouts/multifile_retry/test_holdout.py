import pytest

from src.retry.api import next_delay


def test_intermediate_exponential_delays():
    assert next_delay(2, 2, 20) == 4
    assert next_delay(3, 2, 20) == 8


def test_delay_configuration_must_be_positive():
    with pytest.raises(ValueError):
        next_delay(1, 0, 10)
    with pytest.raises(ValueError):
        next_delay(1, 2, 0)
