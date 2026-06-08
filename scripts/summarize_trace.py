from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


NA = "N/A"


def load_trace(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"trace file does not exist: {path}") from exc
    except OSError as exc:
        raise OSError(f"failed to read trace file {path}: {exc}") from exc

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in trace file {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(f"trace JSON must be an object: {path}")
    return data


def safe_get(data: Any, path: list[str], default: Any = NA) -> Any:
    current = data
    for key in path:
        if not isinstance(current, dict) or key not in current:
            return default
        current = current[key]
    return default if current is None else current


def summarize_trace(trace: dict[str, Any]) -> str:
    final_summary = trace.get("final_summary")
    if not isinstance(final_summary, dict):
        final_summary = {}

    lines = [
        "PyFixAgent Trace Summary",
        "========================",
        "",
        f"Status: {safe_get(final_summary, ['status'])}",
        f"Workspace: {safe_get(trace, ['workspace'])}",
        f"Iterations: {safe_get(final_summary, ['iterations_used'], _iteration_count(trace))}",
        f"Initial failures: {safe_get(final_summary, ['initial_failed'])}",
        f"Final failures: {safe_get(final_summary, ['final_failed'])}",
        f"Modified files: {_format_list(safe_get(final_summary, ['modified_files']))}",
        f"Final test result: {safe_get(final_summary, ['final_test_result'])}",
    ]

    model_line = _top_level_model_line(trace)
    if model_line:
        lines.append(model_line)

    iterations = trace.get("iterations")
    if not isinstance(iterations, list):
        iterations = []

    for index, item in enumerate(iterations, start=1):
        iteration = item if isinstance(item, dict) else {}
        number = safe_get(iteration, ["iteration"], index)
        failure_delta = iteration.get("failure_delta")
        if not isinstance(failure_delta, dict):
            failure_delta = {}
        context_stats = safe_get(iteration, ["context", "stats"], {})
        if not isinstance(context_stats, dict):
            context_stats = {}

        lines.extend(
            [
                "",
                f"Iteration {number}",
                "-----------",
                f"Status: {safe_get(iteration, ['iteration_result', 'status'])}",
                f"Failure type: {safe_get(iteration, ['iteration_result', 'failure_type'])}",
                (
                    "Tests: "
                    f"{_format_failed(safe_get(iteration, ['test_summary_before', 'failed']))} -> "
                    f"{_format_failed(safe_get(iteration, ['test_summary_after', 'failed']))}"
                ),
                f"Fixed: {_count_or_na(failure_delta.get('fixed', NA))}",
                f"Remaining: {_count_or_na(failure_delta.get('remaining', NA))}",
                f"New: {_count_or_na(failure_delta.get('new', NA))}",
                f"Prompt chars: {context_stats.get('prompt_chars', NA)}",
                f"Selected files: {context_stats.get('selected_file_count', NA)}",
                f"Modified files: {_format_list(safe_get(iteration, ['edit_summary', 'modified_files']))}",
                f"Edit count: {safe_get(iteration, ['edit_summary', 'edit_count'])}",
            ]
        )

        model = _iteration_model_line(iteration)
        if model:
            lines.append(model)

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize a PyFixAgent structured trace JSON file.")
    parser.add_argument("trace_path", type=Path, help="Path to a PyFixAgent trace JSON file.")
    args = parser.parse_args(argv)

    try:
        trace = load_trace(args.trace_path)
    except (FileNotFoundError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(summarize_trace(trace))
    return 0


def _iteration_count(trace: dict[str, Any]) -> int:
    iterations = trace.get("iterations")
    return len(iterations) if isinstance(iterations, list) else 0


def _format_list(value: Any) -> str:
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "(none)"
    if value in (None, NA):
        return NA
    return str(value)


def _format_failed(value: Any) -> str:
    return f"{value} failed" if isinstance(value, int) else f"{value} failed" if value != NA else NA


def _count_or_na(value: Any) -> int | str:
    return len(value) if isinstance(value, list) else NA


def _top_level_model_line(trace: dict[str, Any]) -> str:
    iterations = trace.get("iterations")
    if not isinstance(iterations, list):
        return ""
    for item in iterations:
        if isinstance(item, dict):
            line = _iteration_model_line(item)
            if line:
                return line
    return ""


def _iteration_model_line(iteration: dict[str, Any]) -> str:
    provider = safe_get(iteration, ["model_call", "provider"])
    model = safe_get(iteration, ["model_call", "model"])
    if provider == NA and model == NA:
        return ""
    return f"Model: {provider} / {model}"


if __name__ == "__main__":
    raise SystemExit(main())
