from src.collections import ordered_unique


def test_handles_empty_and_numeric_values():
    assert ordered_unique([]) == []
    assert ordered_unique([3, 1, 3, 2, 1]) == [3, 1, 2]
