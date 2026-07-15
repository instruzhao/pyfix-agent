from src.collections import ordered_unique


def test_handles_empty_and_numeric_values():
    assert ordered_unique([]) == []
    assert ordered_unique([4, 1, 4, 2, 1]) == [4, 1, 2]
