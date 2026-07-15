from src.numbers import clamp


def test_clamp_supports_float_boundaries():
    assert clamp(0.25, 0.5, 1.5) == 0.5
    assert clamp(1.25, 0.5, 1.5) == 1.25
