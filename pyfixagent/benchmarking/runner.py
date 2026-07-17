from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import subprocess
import time
from typing import Callable

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.benchmarking.contracts import BenchmarkCase
from pyfixagent.benchmarking.metrics import summarize_runs
from pyfixagent.benchmarking.workspace import HoldoutEvaluator, IsolatedWorkspaceFactory
from pyfixagent.main import save_trace
from pyfixagent.models.base import BaseModel
from pyfixagent.sandbox.local_sandbox import LocalSandbox


def run_benchmark(
    *,
    cases: list[BenchmarkCase],
    project_root: Path,
    output_dir: Path,
    model_factory: Callable[[], BaseModel],
    repeat: int = 5,
    strategy_override: tuple[str, ...] = (),
    keep_workspaces: bool = False,
    sandbox_timeout: int = 30,
    context_line_window: int = 25,
    context_max_files: int = 6,
    context_max_expansion_level: int = 2,
    max_changed_files: int = 8,
    max_changed_lines: int = 400,
    test_commands: tuple[tuple[str, ...], ...] | None = None,
    semantic_review_enabled: bool = False,
    semantic_review_max_revisions: int = 1,
    semantic_review_parse_retries: int = 1,
    semantic_review_max_context_chars: int = 16000,
    semantic_review_max_feedback_chars: int = 3000,
    semantic_review_max_risks: int = 5,
    repository_context_enabled: bool = False,
    repository_max_files: int = 2000,
    repository_max_file_bytes: int = 1_000_000,
    repository_max_graph_depth: int = 2,
    repository_max_related_files: int = 6,
    repository_max_snippet_lines: int = 200,
    context_max_selected_tokens: int = 12000,
) -> dict:
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = output_dir / "traces"
    workspaces = IsolatedWorkspaceFactory(project_root, output_dir)
    holdout_evaluator = HoldoutEvaluator(sandbox_timeout)
    runs: list[dict] = []

    for case in cases:
        strategies = strategy_override or case.strategies
        for strategy in strategies:
            for repetition in range(1, repeat + 1):
                started = time.perf_counter()
                workspace: Path | None = None
                try:
                    workspace = workspaces.prepare(case, strategy, repetition)
                    agent = DefaultAgent(
                        model=model_factory(),
                        sandbox=LocalSandbox(workspace, timeout_seconds=sandbox_timeout),
                        patch_output_dir=output_dir / "patches",
                        max_iterations=case.max_iterations,
                        initial_mode=case.mode,
                        context_strategy=strategy,
                        context_line_window=context_line_window,
                        context_max_files=context_max_files,
                        context_max_expansion_level=context_max_expansion_level,
                        require_clean_workspace=True,
                        allowed_paths=case.allowed_paths,
                        max_changed_files=max_changed_files,
                        max_changed_lines=max_changed_lines,
                        isolate_workspace=True,
                        test_commands=test_commands,
                        semantic_review_enabled=semantic_review_enabled,
                        semantic_review_max_revisions=semantic_review_max_revisions,
                        semantic_review_parse_retries=semantic_review_parse_retries,
                        semantic_review_max_context_chars=semantic_review_max_context_chars,
                        semantic_review_max_feedback_chars=semantic_review_max_feedback_chars,
                        semantic_review_max_risks=semantic_review_max_risks,
                        repository_context_enabled=repository_context_enabled,
                        repository_cache_dir=output_dir / "index",
                        repository_max_files=repository_max_files,
                        repository_max_file_bytes=repository_max_file_bytes,
                        repository_max_graph_depth=repository_max_graph_depth,
                        repository_max_related_files=repository_max_related_files,
                        repository_max_snippet_lines=repository_max_snippet_lines,
                        context_max_selected_tokens=context_max_selected_tokens,
                    )
                    result = agent.run(case.agent_task)
                    candidate_patch = result.candidate_patch or result.patch
                    if result.visible_success and candidate_patch:
                        _apply_exported_patch(workspace, candidate_patch)
                    holdout = holdout_evaluator.run(case, workspace)
                    trace_path = save_trace(result, trace_dir)
                    runs.append(
                        build_run_record(
                            case,
                            strategy,
                            repetition,
                            result,
                            holdout,
                            trace_path,
                            workspace,
                            time.perf_counter() - started,
                        )
                    )
                except Exception as exc:
                    runs.append(build_runner_error(case, strategy, repetition, exc, started))
                finally:
                    if not keep_workspaces and workspace is not None:
                        cleanup_error = workspaces.cleanup(case, workspace)
                        if cleanup_error:
                            run = runs[-1]
                            run["success"] = False
                            run["failure_type"] = "cleanup_error"
                            run["cleanup_error"] = cleanup_error
                            run["error"] = "; ".join(
                                item for item in (run.get("error"), cleanup_error) if item
                            )

    return {
        "schema_version": 3,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize_runs(runs),
        "runs": runs,
    }


def build_run_record(case, strategy, repetition, result, holdout, trace_path, workspace, duration):
    input_tokens = sum(
        int((record.model_call or {}).get("input_tokens") or 0) for record in result.iterations
    )
    output_tokens = sum(
        int((record.model_call or {}).get("output_tokens") or 0) for record in result.iterations
    )
    review_input_tokens = sum(
        int(call.get("input_tokens") or 0)
        for review in (result.reviews or [])
        for call in review.model_calls
    )
    review_output_tokens = sum(
        int(call.get("output_tokens") or 0)
        for review in (result.reviews or [])
        for call in review.model_calls
    )
    input_tokens += review_input_tokens
    output_tokens += review_output_tokens
    visible_success = bool(result.visible_success)
    holdout_success = holdout.get("success")
    candidate_success = visible_success and holdout_success is not False
    success = bool(result.success) and holdout_success is not False
    last_result = result.iterations[-1].iteration_result if result.iterations else None
    if (
        result.success
        and result.acceptance_status in {"accepted", "accepted_with_warnings"}
        and holdout_success is False
    ):
        failure_type = "false_accept"
    elif not result.success and visible_success and holdout_success is True:
        failure_type = "false_reject"
    elif visible_success and holdout_success is False:
        failure_type = "semantic_rejected" if result.acceptance_status == "rejected" else "holdout_failed"
    else:
        failure_type = (last_result or {}).get("failure_type") if last_result else None
    return {
        "case_id": case.case_id,
        "strategy": strategy,
        "repetition": repetition,
        "success": success,
        "candidate_success": candidate_success,
        "visible_success": visible_success,
        "agent_accepted": bool(result.success),
        "acceptance_status": result.acceptance_status,
        "holdout_success": holdout_success,
        "holdout_exit_code": holdout.get("exit_code"),
        "holdout_output": holdout.get("output", ""),
        "error": result.error,
        "iterations": len(result.iterations),
        "iteration_failure_types": [
            (record.iteration_result or {}).get("failure_type") for record in result.iterations
        ],
        "policy_violation_count": sum(
            1
            for record in result.iterations
            if "EDIT_POLICY_REJECTED" in str((record.apply or {}).get("error") or "")
            or "outside allowed paths" in str(record.replacement_error or "")
            or "forbidden path" in str(record.replacement_error or "")
        ),
        "duration_seconds": round(duration, 6),
        "prompt_chars": sum(
            int((record.context or {}).get("stats", {}).get("prompt_chars") or 0)
            for record in result.iterations
        ),
        "selected_context_chars": sum(
            int((record.context or {}).get("stats", {}).get("selected_context_chars") or 0)
            for record in result.iterations
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "review_input_tokens": review_input_tokens,
        "review_output_tokens": review_output_tokens,
        "review_count": len(result.reviews or []),
        "semantic_revisions_used": result.semantic_revisions_used,
        "failure_type": failure_type,
        "trace_path": str(trace_path),
        "workspace": str(workspace),
        "workspace_strategy": result.workspace_strategy,
        "final_patch_path": result.final_patch_path,
        "candidate_patch_path": result.candidate_patch_path,
    }


def build_runner_error(case, strategy, repetition, exc, started):
    return {
        "case_id": case.case_id,
        "strategy": strategy,
        "repetition": repetition,
        "success": False,
        "visible_success": False,
        "holdout_success": None,
        "error": str(exc),
        "iterations": 0,
        "iteration_failure_types": [],
        "policy_violation_count": 0,
        "duration_seconds": round(time.perf_counter() - started, 6),
        "prompt_chars": 0,
        "selected_context_chars": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "failure_type": "runner_error",
        "trace_path": None,
    }


def _apply_exported_patch(workspace: Path, patch: str) -> None:
    for args in (["apply", "--check", "-"], ["apply", "-"]):
        completed = subprocess.run(
            ["git", *args],
            cwd=workspace,
            input=patch.encode("utf-8"),
            timeout=30,
            capture_output=True,
            check=False,
        )
        if completed.returncode != 0:
            message = (
                completed.stderr.decode("utf-8", errors="replace").strip()
                or completed.stdout.decode("utf-8", errors="replace").strip()
            )
            raise RuntimeError(f"exported patch could not be materialized: {message}")
