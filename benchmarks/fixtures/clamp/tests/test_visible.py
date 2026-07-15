from src.numbers import clamp


def test_clamps_below_inside_and_above_range():
    assert clamp(-2, 0, 10) == 0
    assert clamp(5, 0, 10) == 5
    assert clamp(12, 0, 10) == 10
