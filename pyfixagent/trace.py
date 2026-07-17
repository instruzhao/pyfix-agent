from __future__ import annotations

import platform
from pathlib import Path
import re
import sys
import time
from typing import Any

from pyfixagent.context.pytest_summary import PytestSummary, parse_pytest_summary, short_test_result


def failure_delta(before: PytestSummary | None, after: PytestSummary | None) -> dict:
    before_failed = before.failed_tests if before is not None else []
    after_failed = after.failed_tests if after is not None else []
    after_set = set(after_failed)
    before_set = set(before_failed)
    return {
        "fixed": [node for node in before_failed if node not in after_set],
        "remaining": [node for node in before_failed if node in after_set],
        "new": [node for node in after_failed if node not in before_set],
    }


def iteration_result(
    *,
    success: bool,
    mode: str,
    raw_model_output: str,
    model_parse_error: str | None,
    apply_success: bool,
    apply_error: str,
    apply_check_success: bool,
    apply_check_error: str,
    pytest_exit_code: int | None,
    delta: dict,
) -> dict:
    if success:
        return {
            "status": "test_passed",
            "failure_type": "success",
            "reason": "Pytest passed after applying the repair.",
        }

    if model_parse_error:
        return {
            "status": "replacement_parse_failed" if mode == "replacement" else "model_output_invalid",
            "failure_type": "invalid_model_output",
            "reason": model_parse_error,
        }

    if raw_model_output == "":
        return {
            "status": "model_output_invalid",
            "failure_type": "invalid_model_output",
            "reason": "Model did not return usable output.",
        }

    if mode == "patch" and not apply_check_success:
        return {
            "status": "patch_check_failed",
            "failure_type": "invalid_model_output",
            "reason": apply_check_error or "Patch failed git apply --check.",
        }

    if not apply_success:
        return {
            "status": "replacement_apply_failed" if mode == "replacement" else "patch_apply_failed",
            "failure_type": "apply_failed",
            "reason": apply_error or "Repair could not be applied.",
        }

    if pytest_exit_code == 124:
        return {
            "status": "timeout",
            "failure_type": "timeout",
            "reason": "Pytest timed out after applying the repair.",
        }

    if pytest_exit_code is not None and pytest_exit_code != 0:
        if delta.get("new"):
            failure_type = "regression"
        elif delta.get("fixed"):
            failure_type = "incomplete_fix"
        else:
            failure_type = "no_progress"
        return {
            "status": "test_failed_after_apply",
            "failure_type": failure_type,
            "reason": "Repair was applied successfully, but pytest still failed.",
        }

    return {
        "status": "unknown_error",
        "failure_type": "unknown",
        "reason": "Iteration failed before a structured reason could be determined.",
    }


def build_model_output(
    *,
    mode: str,
    raw: str,
    parsed_edits: list[dict] | None,
    parse_error: str | None,
    cleaned_patch: str,
) -> dict:
    data: dict[str, Any] = {
        "mode": mode,
        "raw": raw,
        "parsed_success": parse_error is None and (bool(parsed_edits) if mode == "replacement" else bool(cleaned_patch)),
        "parsed_edits": parsed_edits if mode == "replacement" else None,
        "parse_error": parse_error,
    }
    if mode == "patch":
        data["parsed_patch"] = cleaned_patch
    return data


def build_apply(
    *,
    method: str,
    success: bool,
    error: str,
    generated_diff: str,
    check_success: bool,
    check_error: str,
    command: str,
) -> dict:
    return {
        "method": method,
        "success": success,
        "error": error or None,
        "generated_diff": generated_diff,
        "check_success": check_success,
        "check_error": check_error or None,
        "command": command,
    }


def edit_summary(
    *,
    mode: str,
    replacement_edits: list[dict] | None,
    diff_text: str,
) -> dict:
    if mode == "replacement":
        edits = replacement_edits or []
        modified_files = _dedupe([str(edit.get("path")) for edit in edits if edit.get("path")])
        changed_lines = sum(_replacement_changed_lines(edit) for edit in edits)
        return {
            "modified_files": modified_files,
            "edit_count": len(edits),
            "changed_lines_estimate": changed_lines,
        }

    modified_files = _paths_from_diff(diff_text)
    return {
        "modified_files": modified_files,
        "edit_count": len(modified_files),
        "changed_lines_estimate": _diff_changed_lines(diff_text),
    }


def collect_environment(workspace: str | Path) -> dict:
    try:
        import pytest

        pytest_version = pytest.__version__
    except Exception:
        pytest_version = None

    return {
        "python": platform.python_version(),
        "platform": sys.platform,
        "pytest": pytest_version,
        "cwd": str(Path.cwd()),
        "workspace": str(workspace),
    }


def model_call_metadata(model: Any, duration_seconds: float | None = None) -> dict:
    provider = "mock" if model.__class__.__name__ == "MockModel" else "litellm" if hasattr(model, "model_name") else model.__class__.__name__
    usage = getattr(model, "last_usage", {}) or {}
    extra_body = getattr(model, "extra_body", None) or {}
    return {
        "provider": provider,
        "model": getattr(model, "model_name", model.__class__.__name__),
        "temperature": getattr(model, "temperature", None),
        "max_tokens": getattr(model, "max_tokens", None),
        "timeout": getattr(model, "timeout_seconds", None),
        "duration_seconds": duration_seconds,
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "total_tokens": usage.get("total_tokens"),
        "enable_thinking": extra_body.get("enable_thinking"),
        "thinking_budget": extra_body.get("thinking_budget"),
    }


def timed_model_call(model: Any, system_prompt: str, user_prompt: str) -> tuple[str, dict]:
    start = time.perf_counter()
    try:
        output = model.generate_patch(system_prompt, user_prompt)
    finally:
        duration = time.perf_counter() - start
    return output, model_call_metadata(model, duration)


def final_summary(result: Any) -> dict:
    iterations = list(getattr(result, "iterations", []) or [])
    initial = parse_pytest_summary(getattr(result, "test_output_before", ""))
    final = parse_pytest_summary(getattr(result, "test_output_after", "") or getattr(result, "test_output_before", ""))
    modified_files: list[str] = []
    for record in iterations:
        summary = getattr(record, "edit_summary", None) or {}
        for path in summary.get("modified_files", []):
            if path not in modified_files:
                modified_files.append(path)

    acceptance_status = getattr(result, "acceptance_status", "not_run")
    if getattr(result, "success", False):
        status = "passed"
    elif getattr(result, "visible_success", False) and acceptance_status not in {"disabled", "not_run"}:
        status = "needs_review"
    elif getattr(result, "error", None):
        status = "error" if not iterations else "failed"
    else:
        status = "failed"

    return {
        "status": status,
        "iterations_used": len(iterations),
        "initial_total": initial.total,
        "initial_failed": initial.failed,
        "final_total": final.total,
        "final_failed": final.failed,
        "modified_files": modified_files,
        "final_test_result": short_test_result(final),
        "visible_success": bool(getattr(result, "visible_success", False)),
        "acceptance_status": acceptance_status,
        "review_count": len(getattr(result, "reviews", []) or []),
        "semantic_revisions_used": int(getattr(result, "semantic_revisions_used", 0) or 0),
    }


def _replacement_changed_lines(edit: dict) -> int:
    old_lines = str(edit.get("old", "")).splitlines()
    new_lines = str(edit.get("new", "")).splitlines()
    return max(len(old_lines), len(new_lines))


def _diff_changed_lines(diff_text: str) -> int:
    count = 0
    for line in diff_text.splitlines():
        if line.startswith(("+++", "---")):
            continue
        if line.startswith(("+", "-")):
            count += 1
    return count


def _paths_from_diff(diff_text: str) -> list[str]:
    paths: list[str] = []
    for line in diff_text.splitlines():
        match = re.match(r"^diff --git a/(.*?) b/(.*?)$", line)
        if match:
            paths.append(match.group(2).replace("\\", "/"))
    return _dedupe(paths)


def _dedupe(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value not in result:
            result.append(value)
    return result
