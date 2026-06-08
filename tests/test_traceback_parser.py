from pyfixagent.context.traceback_parser import parse_pytest_failure_output


def test_parse_single_assertion_failure():
    output = """
FAILED tests/test_data.py::test_load_data - AssertionError: assert 0.7 > 0.9
tests/test_data.py:12: in test_load_data
ml_iris_tree/data.py:28: in load_data
E   AssertionError: assert 0.7 > 0.9
"""

    summary = parse_pytest_failure_output(output)

    assert summary.failed_tests == ["tests/test_data.py::test_load_data"]
    assert summary.exception_type == "AssertionError"
    assert summary.error_message == "assert 0.7 > 0.9"
    assert [(frame.path, frame.line, frame.function) for frame in summary.frames] == [
        ("tests/test_data.py", 12, "test_load_data"),
        ("ml_iris_tree/data.py", 28, "load_data"),
    ]


def test_parse_multiple_failed_tests_and_value_error():
    output = """
FAILED tests/test_data.py::test_load_data - ValueError: bad value
FAILED tests/test_metrics.py::test_accuracy - TypeError: bad type
tests/test_data.py:5: in test_load_data
ml_iris_tree/data.py:8: in load_data
E   ValueError: bad value
"""

    summary = parse_pytest_failure_output(output)

    assert summary.failed_tests == [
        "tests/test_data.py::test_load_data",
        "tests/test_metrics.py::test_accuracy",
    ]
    assert summary.exception_type == "ValueError"
    assert summary.error_message == "bad value"
    assert summary.frames[-1].path == "ml_iris_tree/data.py"
    assert summary.frames[-1].line == 8


def test_parse_empty_or_unstructured_output_does_not_crash():
    summary = parse_pytest_failure_output("")

    assert summary.failed_tests == []
    assert summary.exception_type is None
    assert summary.error_message is None
    assert summary.frames == []


def test_parse_windows_style_frame_path():
    output = r"""
C:\repo\project\tests\test_app.py:7: in test_app
E   RuntimeError: boom
"""

    summary = parse_pytest_failure_output(output)

    assert summary.frames[0].path == "C:/repo/project/tests/test_app.py"
    assert summary.frames[0].line == 7
    assert summary.exception_type == "RuntimeError"
