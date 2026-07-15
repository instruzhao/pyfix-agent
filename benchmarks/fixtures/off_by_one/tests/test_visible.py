from src.paging import page_items


def test_first_page_contains_full_page():
    assert page_items([1, 2, 3, 4, 5], page=1, page_size=3) == [1, 2, 3]
