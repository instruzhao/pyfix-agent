import json

from pyfixagent.main import save_trace
from pyfixagent.schemas import AgentResult, IterationRecord
from pyfixagent.trace_redaction import TraceRedactor


def test_path_redaction_preserves_relative_evidence_and_replaces_local_roots(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    data = {
        "workspace": str(workspace),
        "prompt": f"Read {workspace / 'src' / 'app.py'} and src/app.py",
    }

    redacted = TraceRedactor("paths").redact(data, workspace=workspace)

    assert str(tmp_path) not in json.dumps(redacted)
    assert "<workspace>" in redacted["prompt"]
    assert "src/app.py" in redacted["prompt"]
    assert redacted["trace_redaction"]["mode"] == "paths"


def test_safe_redaction_hashes_source_bearing_fields_but_keeps_metrics(tmp_path):
    data = {
        "task": "private task",
        "success": True,
        "iterations": [
            {
                "prompt": "secret source",
                "replacement_edits": [{"path": "src/app.py", "old": "secret old", "new": "secret new"}],
                "model_call": {"input_tokens": 12},
            }
        ],
    }

    redacted = TraceRedactor("safe").redact(data, workspace=tmp_path)

    serialized = json.dumps(redacted)
    assert "private task" not in serialized
    assert "secret source" not in serialized
    assert "secret old" not in serialized
    assert "secret new" not in serialized
    assert redacted["success"] is True
    assert redacted["iterations"][0]["model_call"]["input_tokens"] == 12
    assert redacted["trace_redaction"]["redacted_fields"] == [
        "prompt",
        "replacement_edits",
        "task",
    ]


def test_save_trace_can_write_safe_redacted_agent_result(tmp_path):
    result = AgentResult(
        task="private task",
        workspace=str(tmp_path / "workspace"),
        success=False,
        patch_applied=False,
        test_output_before="secret failure",
        test_output_after="",
        patch="secret patch",
        iterations=[
            IterationRecord(
                iteration=1,
                prompt="secret prompt",
                raw_model_output="secret output",
                cleaned_patch="",
                patch_path="",
                apply_check_success=False,
                apply_check_error="",
                apply_success=False,
                apply_error="",
                pytest_exit_code=None,
                pytest_output="secret pytest",
                success=False,
                duration_seconds=0.1,
            )
        ],
    )

    path = save_trace(result, tmp_path / "traces", redaction_mode="safe")
    content = path.read_text(encoding="utf-8")

    assert "private task" not in content
    assert "secret prompt" not in content
    assert json.loads(content)["trace_redaction"]["mode"] == "safe"
