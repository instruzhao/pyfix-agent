from src.stats import median


def test_median_for_odd_and_unsorted_values():
    assert median([9, 1, 4]) == 4
    assert median([2, 8]) == 5.0
