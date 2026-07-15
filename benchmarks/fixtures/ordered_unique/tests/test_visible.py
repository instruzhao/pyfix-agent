from src.collections import ordered_unique


def test_removes_duplicates_without_reordering():
    assert ordered_unique([3, 1, 3, 2, 1]) == [3, 1, 2]
