from src.paths import replace_extension


def test_replaces_only_final_extension():
    assert replace_extension("archive.tar.gz", "zip") == "archive.tar.zip"
