from src.stats import median


def test_median_for_even_number_of_values():
    assert median([7, 1, 3, 5]) == 4.0
