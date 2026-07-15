from src.paths import replace_extension


def test_handles_names_without_extension_and_dot_prefix():
    assert replace_extension("README", "md") == "README.md"
    assert replace_extension("report.txt", ".csv") == "report.csv"
