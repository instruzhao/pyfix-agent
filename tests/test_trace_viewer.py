import json

from pyfixagent.trace_redaction import TraceRedactor
from pyfixagent.trace_viewer import audit_trace, main, render_trace_html


def _trace():
    return {
        "trace_schema_version": "1.5",
        "workspace": "C:\\Users\\private\\repo",
        "task": "fix <script>alert(1)</script>",
        "iterations": [
            {
                "iteration": 1,
                "mode": "replacement",
                "prompt": "private prompt",
                "raw_model_output": "private output",
                "pytest_exit_code": 0,
                "iteration_result": {"failure_type": "success"},
                "model_call": {"model": "model-a"},
            }
        ],
        "reviews": [],
        "final_summary": {"status": "passed"},
    }


def test_trace_audit_detects_absolute_paths_and_missing_redaction():
    trace = _trace()
    trace["trace_redaction"] = {"mode": "none"}

    audit = audit_trace(trace)

    assert audit.passed is False
    assert audit.absolute_path_findings
    assert "no path or source-content redaction" in audit.warnings[0]


def test_safe_redacted_trace_passes_audit():
    trace = TraceRedactor("safe").redact(_trace(), workspace="C:\\Users\\private\\repo")

    audit = audit_trace(trace)

    assert audit.passed is True
    assert audit.redaction_mode == "safe"
    assert not audit.unsafe_content_fields


def test_viewer_escapes_trace_content_and_has_no_script_execution():
    trace = TraceRedactor("safe").redact(_trace(), workspace="C:\\Users\\private\\repo")

    rendered = render_trace_html(trace, audit_trace(trace))

    assert "PyFixAgent trace" in rendered
    assert "<script>alert(1)</script>" not in rendered
    assert "default-src 'none'" in rendered
    assert "model-a" in rendered


def test_trace_viewer_cli_can_apply_safe_redaction(tmp_path):
    trace_path = tmp_path / "trace.json"
    output_path = tmp_path / "trace.html"
    trace_path.write_text(json.dumps(_trace()), encoding="utf-8")

    exit_code = main(
        [str(trace_path), "--output", str(output_path), "--redaction", "safe", "--fail-on-audit"]
    )

    assert exit_code == 0
    content = output_path.read_text(encoding="utf-8")
    assert "private prompt" not in content
    assert "Privacy audit" in content
