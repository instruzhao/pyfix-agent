from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from html import escape
import json
from pathlib import Path
import re
import sys
from typing import Any

from pyfixagent.trace_redaction import TraceRedactor


_SOURCE_KEYS = {
    "task",
    "prompt",
    "raw_model_output",
    "cleaned_patch",
    "pytest_output",
    "test_output_before",
    "test_output_after",
    "patch",
    "candidate_patch",
    "replacement_raw_output",
    "generated_diff",
}
_SOURCE_CONTAINER_KEYS = {"model_output", "replacement_edits"}
_REDACTED_MARKER = re.compile(r"^<redacted sha256=[0-9a-f]{16} chars=[0-9]+>$")
_ABSOLUTE_PATHS = (
    re.compile(r"(?i)\b[A-Z]:[\\/][^\s\"'<>]+"),
    re.compile(r"/(?:Users|home|private/tmp|var/folders)/[^\s\"'<>]+"),
)


@dataclass(frozen=True)
class TraceAudit:
    passed: bool
    redaction_mode: str
    absolute_path_findings: tuple[str, ...]
    unsafe_content_fields: tuple[str, ...]
    warnings: tuple[str, ...]


def audit_trace(trace: dict[str, Any]) -> TraceAudit:
    redaction = trace.get("trace_redaction")
    mode = str(redaction.get("mode", "unknown")) if isinstance(redaction, dict) else "unknown"
    absolute_paths: list[str] = []
    unsafe_content: list[str] = []
    _audit_value(trace, "$", mode, absolute_paths, unsafe_content)
    warnings: list[str] = []
    if mode == "none":
        warnings.append("trace has no path or source-content redaction")
    elif mode == "paths":
        warnings.append("path-redacted traces can still contain source code and model output")
    elif mode == "unknown":
        warnings.append("trace does not declare a redaction mode")
    passed = not absolute_paths and not unsafe_content
    return TraceAudit(
        passed=passed,
        redaction_mode=mode,
        absolute_path_findings=tuple(dict.fromkeys(absolute_paths))[:20],
        unsafe_content_fields=tuple(dict.fromkeys(unsafe_content))[:20],
        warnings=tuple(warnings),
    )


def render_trace_html(trace: dict[str, Any], audit: TraceAudit) -> str:
    summary = trace.get("final_summary") if isinstance(trace.get("final_summary"), dict) else {}
    iterations = trace.get("iterations") if isinstance(trace.get("iterations"), list) else []
    reviews = trace.get("reviews") if isinstance(trace.get("reviews"), list) else []
    status = str(summary.get("status", "unknown"))
    audit_class = "ok" if audit.passed else "warning"
    rows = []
    for index, raw in enumerate(iterations, start=1):
        item = raw if isinstance(raw, dict) else {}
        result = item.get("iteration_result") if isinstance(item.get("iteration_result"), dict) else {}
        model_call = item.get("model_call") if isinstance(item.get("model_call"), dict) else {}
        rows.append(
            "<tr>"
            f"<td>{escape(str(item.get('iteration', index)))}</td>"
            f"<td>{escape(str(item.get('mode', 'N/A')))}</td>"
            f"<td>{escape(str(result.get('failure_type', 'N/A')))}</td>"
            f"<td>{escape(str(item.get('pytest_exit_code', 'N/A')))}</td>"
            f"<td>{escape(str(model_call.get('model', 'N/A')))}</td>"
            "</tr>"
        )
    audit_items = [
        *(f"Absolute path: {item}" for item in audit.absolute_path_findings),
        *(f"Unsafe source field: {item}" for item in audit.unsafe_content_fields),
        *audit.warnings,
    ]
    audit_html = "".join(f"<li>{escape(item)}</li>" for item in audit_items) or "<li>No findings.</li>"
    raw_json = escape(json.dumps(trace, ensure_ascii=False, indent=2))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>PyFixAgent trace</title>
  <style>
    body {{ font-family: system-ui, sans-serif; max-width: 1100px; margin: 2rem auto; padding: 0 1rem; color: #172033; }}
    .cards {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(160px,1fr)); gap: .8rem; }}
    .card, section {{ border: 1px solid #d7deea; border-radius: 10px; padding: 1rem; margin: 1rem 0; }}
    .label {{ color: #596579; font-size: .8rem; text-transform: uppercase; }}
    .value {{ font-size: 1.2rem; font-weight: 650; overflow-wrap: anywhere; }}
    .ok {{ border-left: 5px solid #16803c; }} .warning {{ border-left: 5px solid #b45309; }}
    table {{ width: 100%; border-collapse: collapse; }} th, td {{ padding: .55rem; text-align: left; border-bottom: 1px solid #e3e8f0; }}
    pre {{ white-space: pre-wrap; overflow-wrap: anywhere; background: #f5f7fa; padding: 1rem; border-radius: 8px; }}
  </style>
</head>
<body>
  <h1>PyFixAgent trace</h1>
  <div class="cards">
    <div class="card"><div class="label">Status</div><div class="value">{escape(status)}</div></div>
    <div class="card"><div class="label">Schema</div><div class="value">{escape(str(trace.get('trace_schema_version', 'N/A')))}</div></div>
    <div class="card"><div class="label">Iterations</div><div class="value">{len(iterations)}</div></div>
    <div class="card"><div class="label">Reviews</div><div class="value">{len(reviews)}</div></div>
    <div class="card"><div class="label">Redaction</div><div class="value">{escape(audit.redaction_mode)}</div></div>
  </div>
  <section class="{audit_class}"><h2>Privacy audit</h2><ul>{audit_html}</ul></section>
  <section><h2>Iterations</h2><table><thead><tr><th>#</th><th>Mode</th><th>Result</th><th>pytest</th><th>Model</th></tr></thead><tbody>{''.join(rows)}</tbody></table></section>
  <section><details><summary>Structured trace JSON</summary><pre>{raw_json}</pre></details></section>
</body>
</html>
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit and render a standalone PyFixAgent trace viewer.")
    parser.add_argument("trace_path", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--redaction",
        choices=["preserve", "paths", "safe"],
        default="preserve",
        help="Optionally apply redaction before embedding the trace in HTML.",
    )
    parser.add_argument("--fail-on-audit", action="store_true")
    args = parser.parse_args(argv)
    try:
        trace = json.loads(args.trace_path.read_text(encoding="utf-8"))
        if not isinstance(trace, dict):
            raise ValueError("trace JSON must be an object")
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.redaction != "preserve":
        trace = TraceRedactor(args.redaction).redact(trace, workspace=trace.get("workspace"))
    audit = audit_trace(trace)
    output = args.output or args.trace_path.with_suffix(".html")
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(render_trace_html(trace, audit), encoding="utf-8", newline="\n")
    except OSError as exc:
        print(f"error: failed to write viewer: {exc}", file=sys.stderr)
        return 1
    print(f"Trace viewer: {output}")
    print(f"Privacy audit: {'passed' if audit.passed else 'findings detected'}")
    return 2 if args.fail_on_audit and not audit.passed else 0


def _audit_value(
    value: Any,
    path: str,
    mode: str,
    absolute_paths: list[str],
    unsafe_content: list[str],
    key: str = "",
) -> None:
    if mode == "safe" and key in _SOURCE_KEYS and isinstance(value, str) and value:
        if not _REDACTED_MARKER.fullmatch(value):
            unsafe_content.append(path)
    if mode == "safe" and key in _SOURCE_CONTAINER_KEYS and value:
        if not (isinstance(value, str) and _REDACTED_MARKER.fullmatch(value)):
            unsafe_content.append(path)
    if isinstance(value, dict):
        for item_key, item in value.items():
            _audit_value(item, f"{path}.{item_key}", mode, absolute_paths, unsafe_content, item_key)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _audit_value(item, f"{path}[{index}]", mode, absolute_paths, unsafe_content, key)
        return
    if isinstance(value, str):
        for pattern in _ABSOLUTE_PATHS:
            absolute_paths.extend(match.group(0) for match in pattern.finditer(value))


def cli() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
