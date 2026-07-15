from src.text import slugify


def test_slug_collapses_whitespace_and_hyphens():
    assert slugify("  Multi   Word -- Title  ") == "multi-word-title"
