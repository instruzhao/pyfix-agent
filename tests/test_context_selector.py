from pyfixagent.context.selector import select_context
from pyfixagent.context.traceback_parser import PytestFailureSummary, TraceFrame


def test_select_context_uses_failed_test_and_traceback_source(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "pkg").mkdir()
    (workspace / "tests" / "test_app.py").write_text("from pkg.app import value\n\ndef test_value():\n    assert value() == 2\n", encoding="utf-8")
    (workspace / "pkg" / "app.py").write_text("def value():\n    return 1\n", encoding="utf-8")
    summary = PytestFailureSummary(
        failed_tests=["tests/test_app.py::test_value"],
        exception_type="AssertionError",
        error_message="assert 1 == 2",
        frames=[
            TraceFrame("tests/test_app.py", 4, "test_value"),
            TraceFrame("pkg/app.py", 2, "value"),
        ],
        raw_output="",
    )

    context = select_context(summary, workspace, line_window=1, max_files=6)

    assert context.strategy == "traceback"
    assert context.fallback_used is False
    assert [snippet.path for snippet in context.snippets] == ["tests/test_app.py", "pkg/app.py"]
    assert context.snippets[0].reason == "failing_test_file"
    assert context.snippets[0].start_line == 3
    assert context.snippets[1].reason == "traceback_source_file"


def test_select_context_deduplicates_and_limits_max_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    for name in ("a.py", "b.py", "c.py"):
        (workspace / name).write_text("line1\nline2\nline3\n", encoding="utf-8")
    summary = PytestFailureSummary(
        failed_tests=[],
        exception_type=None,
        error_message=None,
        frames=[
            TraceFrame("a.py", 1),
            TraceFrame("a.py", 3),
            TraceFrame("b.py", 2),
            TraceFrame("c.py", 2),
        ],
        raw_output="",
    )

    context = select_context(summary, workspace, line_window=0, max_files=2)

    assert [snippet.path for snippet in context.snippets] == ["a.py", "b.py"]
    assert context.snippets[0].start_line == 1
    assert context.snippets[0].end_line == 3


def test_select_context_rejects_outside_paths_and_falls_back_to_full(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    summary = PytestFailureSummary(
        failed_tests=[],
        exception_type=None,
        error_message=None,
        frames=[TraceFrame("../outside.py", 1)],
        raw_output="",
    )

    context = select_context(summary, workspace, fallback_to_full_context=True)

    assert context.strategy == "traceback"
    assert context.fallback_used is True
    assert [snippet.path for snippet in context.snippets] == ["app.py"]


def test_select_context_includes_modules_imported_by_failing_tests(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "src").mkdir()
    (workspace / "tests" / "test_billing.py").write_text(
        "from src.billing import calculate_order_total\n\n"
        "def test_total():\n"
        "    assert calculate_order_total([]) == 0\n",
        encoding="utf-8",
    )
    (workspace / "src" / "billing.py").write_text(
        "def calculate_order_total(items):\n"
        "    return 1\n",
        encoding="utf-8",
    )
    summary = PytestFailureSummary(
        failed_tests=["tests/test_billing.py::test_total"],
        exception_type="AssertionError",
        error_message="assert 1 == 0",
        frames=[TraceFrame("tests/test_billing.py", 4, "test_total")],
        raw_output="",
    )

    context = select_context(summary, workspace, line_window=1, max_files=6)

    assert [snippet.path for snippet in context.snippets] == ["tests/test_billing.py", "src/billing.py"]
    assert context.snippets[1].reason == "direct_test_import"
