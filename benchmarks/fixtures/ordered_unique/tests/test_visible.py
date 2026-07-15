from src.collections import ordered_unique


def test_removes_duplicates_without_reordering():
    assert ordered_unique(["b", "a", "b", "c", "a"]) == ["b", "a", "c"]
