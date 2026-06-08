from pyfixagent.context.pytest_summary import parse_pytest_summary, short_test_result


def test_parse_pytest_summary_with_failures_and_windows_paths():
    output = r"""
collected 6 items
tests\test_data.py F
FAILED tests\test_data.py::test_x - AssertionError
FAILED tests/test_model.py::test_y - AssertionError
========================= 2 failed, 4 passed in 0.25s =========================
"""

    summary = parse_pytest_summary(output)

    assert summary.total == 6
    assert summary.failed == 2
    assert summary.passed == 4
    assert summary.skipped == 0
    assert summary.failed_tests == ["tests/test_data.py::test_x", "tests/test_model.py::test_y"]


def test_parse_pytest_summary_with_all_passed():
    summary = parse_pytest_summary("collected 6 items\n============================== 6 passed in 0.07s ==============================")

    assert summary.total == 6
    assert summary.passed == 6
    assert summary.failed == 0
    assert summary.failed_tests == []
    assert short_test_result(summary) == "6 passed"


def test_parse_pytest_summary_with_failed_passed_and_skipped():
    summary = parse_pytest_summary("1 failed, 5 passed, 1 skipped in 1.0s")

    assert summary.total == 7
    assert summary.failed == 1
    assert summary.passed == 5
    assert summary.skipped == 1


def test_parse_pytest_summary_empty_output_does_not_crash():
    summary = parse_pytest_summary("")

    assert summary.total is None
    assert summary.passed == 0
    assert summary.failed == 0
    assert summary.skipped == 0
    assert summary.failed_tests == []
