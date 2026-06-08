import json
import importlib.util
from pathlib import Path
import subprocess
import sys


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "summarize_trace.py"
SPEC = importlib.util.spec_from_file_location("summarize_trace", SCRIPT_PATH)
assert SPEC is not None
summarize_trace_module = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(summarize_trace_module)
main = summarize_trace_module.main
summarize_trace = summarize_trace_module.summarize_trace


def minimal_trace():
    return {
        "workspace": "workspaces/demo_project",
        "final_summary": {
            "status": "passed",
            "iterations_used": 2,
            "initial_failed": 3,
            "final_failed": 0,
            "modified_files": ["src/billing.py"],
            "final_test_result": "6 passed",
        },
        "iterations": [
            {
                "iteration": 1,
                "iteration_result": {
                    "status": "test_failed_after_apply",
                    "failure_type": "incomplete_fix",
                },
                "test_summary_before": {"failed": 3},
                "test_summary_after": {"failed": 1},
                "failure_delta": {
                    "fixed": ["a", "b"],
                    "remaining": ["c"],
                    "new": [],
                },
                "context": {
                    "strategy": "traceback",
                    "stats": {
                        "prompt_chars": 12036,
                        "selected_file_count": 2,
                    },
                },
                "edit_summary": {
                    "modified_files": ["src/billing.py"],
                    "edit_count": 1,
                },
                "model_call": {
                    "provider": "litellm",
                    "model": "openai/glm-5",
                },
            }
        ],
    }


def write_trace(tmp_path, data):
    path = tmp_path / "trace.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_summarize_trace_includes_status_iterations_and_modified_files():
    output = summarize_trace(minimal_trace())

    assert "Status: passed" in output
    assert "Iterations: 2" in output
    assert "Modified files: src/billing.py" in output


def test_summarize_trace_displays_iteration_details():
    trace = minimal_trace()
    trace["iterations"].append(
        {
            "iteration": 2,
            "iteration_result": {"status": "test_passed", "failure_type": "success"},
            "test_summary_before": {"failed": 1},
            "test_summary_after": {"failed": 0},
            "failure_delta": {"fixed": ["c"], "remaining": [], "new": []},
            "context": {"stats": {"prompt_chars": 9458, "selected_file_count": 2}},
            "edit_summary": {"modified_files": ["src/billing.py"], "edit_count": 1},
        }
    )

    output = summarize_trace(trace)

    assert "Iteration 1" in output
    assert "Failure type: incomplete_fix" in output
    assert "Tests: 3 failed -> 1 failed" in output
    assert "Fixed: 2" in output
    assert "Iteration 2" in output
    assert "Failure type: success" in output
    assert "Tests: 1 failed -> 0 failed" in output


def test_summarize_trace_handles_missing_optional_fields():
    output = summarize_trace({"workspace": "workspace", "iterations": [{}]})

    assert "Status: N/A" in output
    assert "Iterations: 1" in output
    assert "Prompt chars: N/A" in output
    assert "Selected files: N/A" in output


def test_main_reads_trace_file(tmp_path, capsys):
    path = write_trace(tmp_path, minimal_trace())

    assert main([str(path)]) == 0
    captured = capsys.readouterr()
    assert "PyFixAgent Trace Summary" in captured.out
    assert "Status: passed" in captured.out


def test_main_returns_error_for_missing_file(tmp_path, capsys):
    missing = tmp_path / "missing.json"

    assert main([str(missing)]) == 1
    captured = capsys.readouterr()
    assert "trace file does not exist" in captured.err


def test_main_returns_error_for_invalid_json(tmp_path, capsys):
    path = tmp_path / "bad.json"
    path.write_text("{not json", encoding="utf-8")

    assert main([str(path)]) == 1
    captured = capsys.readouterr()
    assert "invalid JSON" in captured.err


def test_script_help_is_available():
    completed = subprocess.run(
        [sys.executable, "scripts/summarize_trace.py", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "Summarize a PyFixAgent structured trace" in completed.stdout
