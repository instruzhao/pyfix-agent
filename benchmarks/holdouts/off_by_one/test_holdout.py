from src.paging import page_items


def test_later_and_partial_pages():
    values = [1, 2, 3, 4, 5]
    assert page_items(values, page=2, page_size=2) == [3, 4]
    assert page_items(values, page=3, page_size=2) == [5]
