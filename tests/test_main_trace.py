import json

from pyfixagent.main import save_trace
from pyfixagent.schemas import AgentResult, IterationRecord


def test_save_trace_writes_agent_result_json(tmp_path):
    result = AgentResult(
        task="Fix tests",
        workspace="workspaces/demo_project",
        success=False,
        patch_applied=False,
        test_output_before="before",
        test_output_after="after",
        patch="patch",
        iterations=[
            IterationRecord(
                iteration=1,
                prompt="prompt",
                raw_model_output="raw",
                cleaned_patch="patch",
                patch_path="outputs/patches/example.patch",
                apply_check_success=False,
                apply_check_error="check failed",
                apply_success=False,
                apply_error="",
                pytest_exit_code=None,
                pytest_output="",
                success=False,
                duration_seconds=1.25,
                patch_command="git apply --check -",
                context={
                    "strategy": "traceback",
                    "fallback_used": False,
                    "prompt_chars": 100,
                    "selected_files": [
                        {
                            "path": "app.py",
                            "reason": "traceback_source_file",
                            "line_range": [1, 10],
                        }
                    ],
                },
            )
        ],
        workspace_strategy="incremental_repair",
        final_patch_command="git diff --",
        error="failed",
    )

    trace_path = save_trace(result, tmp_path)

    data = json.loads(trace_path.read_text(encoding="utf-8"))
    assert data["task"] == "Fix tests"
    assert data["workspace"] == "workspaces/demo_project"
    assert data["success"] is False
    assert data["workspace_strategy"] == "incremental_repair"
    assert data["final_patch_command"] == "git diff --"
    assert data["iterations"][0]["apply_check_error"] == "check failed"
    assert data["iterations"][0]["model_output_type"] == "patch"
    assert data["iterations"][0]["patch_command"] == "git apply --check -"
    assert data["iterations"][0]["context"]["strategy"] == "traceback"
    assert data["iterations"][0]["context"]["selected_files"][0]["line_range"] == [1, 10]
    assert data["environment"]["python"]
    assert data["environment"]["workspace"] == "workspaces/demo_project"
    assert data["final_summary"]["status"] == "failed"
    assert data["final_summary"]["iterations_used"] == 1
