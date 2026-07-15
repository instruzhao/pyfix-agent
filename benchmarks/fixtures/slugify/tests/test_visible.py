from src.text import slugify


def test_slug_removes_punctuation():
    assert slugify("Hello, World!") == "hello-world"
