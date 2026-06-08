from types import SimpleNamespace

from pyfixagent.context.pytest_summary import PytestSummary
from pyfixagent.schemas import IterationRecord
from pyfixagent.trace import (
    collect_environment,
    edit_summary,
    failure_delta,
    final_summary,
    iteration_result,
    model_call_metadata,
)


def test_failure_delta_tracks_fixed_remaining_and_new():
    before = PytestSummary(
        total=3,
        passed=0,
        failed=3,
        skipped=0,
        failed_tests=["tests/test_a.py::test_a", "tests/test_b.py::test_b", "tests/test_c.py::test_c"],
    )
    after = PytestSummary(
        total=3,
        passed=2,
        failed=2,
        skipped=0,
        failed_tests=["tests/test_c.py::test_c", "tests/test_d.py::test_d"],
    )

    delta = failure_delta(before, after)

    assert delta["fixed"] == ["tests/test_a.py::test_a", "tests/test_b.py::test_b"]
    assert delta["remaining"] == ["tests/test_c.py::test_c"]
    assert delta["new"] == ["tests/test_d.py::test_d"]


def test_iteration_result_distinguishes_incomplete_fix_regression_and_success():
    incomplete = iteration_result(
        success=False,
        mode="replacement",
        raw_model_output="[]",
        model_parse_error=None,
        apply_success=True,
        apply_error="",
        apply_check_success=False,
        apply_check_error="",
        pytest_exit_code=1,
        delta={"fixed": ["a"], "remaining": ["b"], "new": []},
    )
    regression = iteration_result(
        success=False,
        mode="replacement",
        raw_model_output="[]",
        model_parse_error=None,
        apply_success=True,
        apply_error="",
        apply_check_success=False,
        apply_check_error="",
        pytest_exit_code=1,
        delta={"fixed": [], "remaining": ["b"], "new": ["c"]},
    )
    success = iteration_result(
        success=True,
        mode="replacement",
        raw_model_output="[]",
        model_parse_error=None,
        apply_success=True,
        apply_error="",
        apply_check_success=False,
        apply_check_error="",
        pytest_exit_code=0,
        delta={"fixed": ["a"], "remaining": [], "new": []},
    )

    assert incomplete["failure_type"] == "incomplete_fix"
    assert regression["failure_type"] == "regression"
    assert success["failure_type"] == "success"


def test_edit_summary_for_replacement_and_diff():
    replacement = edit_summary(
        mode="replacement",
        replacement_edits=[
            {"path": "pkg/a.py", "old": "x = 1\n", "new": "x = 2\n"},
            {"path": "pkg/b.py", "old": "y = 1\n", "new": "y = 2\ny = 3\n"},
        ],
        diff_text="",
    )
    patch = edit_summary(
        mode="patch",
        replacement_edits=None,
        diff_text=(
            "diff --git a/pkg/a.py b/pkg/a.py\n"
            "--- a/pkg/a.py\n"
            "+++ b/pkg/a.py\n"
            "@@ -1 +1 @@\n"
            "-x = 1\n"
            "+x = 2\n"
        ),
    )

    assert replacement["modified_files"] == ["pkg/a.py", "pkg/b.py"]
    assert replacement["edit_count"] == 2
    assert replacement["changed_lines_estimate"] == 3
    assert patch["modified_files"] == ["pkg/a.py"]
    assert patch["changed_lines_estimate"] == 2


def test_environment_and_model_call_metadata_are_best_effort(tmp_path):
    class MiniModel:
        model_name = "mini"
        temperature = 0.0
        max_tokens = 10
        timeout_seconds = 5

    env = collect_environment(tmp_path)
    model_call = model_call_metadata(MiniModel(), duration_seconds=1.25)

    assert env["python"]
    assert env["platform"]
    assert env["workspace"] == str(tmp_path)
    assert model_call["model"] == "mini"
    assert model_call["duration_seconds"] == 1.25


def test_final_summary_rolls_up_iterations():
    record = IterationRecord(
        iteration=1,
        prompt="prompt",
        raw_model_output="raw",
        cleaned_patch="diff",
        patch_path="patch",
        apply_check_success=False,
        apply_check_error="",
        apply_success=True,
        apply_error="",
        pytest_exit_code=0,
        pytest_output="6 passed",
        success=True,
        duration_seconds=1.0,
        edit_summary={"modified_files": ["pkg/a.py"], "edit_count": 1, "changed_lines_estimate": 1},
    )
    result = SimpleNamespace(
        success=True,
        error=None,
        test_output_before="collected 6 items\nFAILED tests/test_a.py::test_a\n1 failed, 5 passed",
        test_output_after="6 passed",
        iterations=[record],
    )

    summary = final_summary(result)

    assert summary["status"] == "passed"
    assert summary["iterations_used"] == 1
    assert summary["initial_failed"] == 1
    assert summary["final_failed"] == 0
    assert summary["modified_files"] == ["pkg/a.py"]
    assert summary["final_test_result"] == "6 passed"
