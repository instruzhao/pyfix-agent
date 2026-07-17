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
    review_model_factory: Callable[[], BaseModel] | None = None,
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
    semantic_review_max_contracts: int = 3,
    repository_context_enabled: bool = False,
    repository_modes: tuple[bool, ...] | None = None,
    repository_max_files: int = 2000,
    repository_max_file_bytes: int = 1_000_000,
    repository_max_graph_depth: int = 2,
    repository_max_related_files: int = 6,
    repository_max_snippet_lines: int = 200,
    context_max_selected_tokens: int = 12000,
    trace_redaction_mode: str = "paths",
) -> dict:
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = output_dir / "traces"
    workspaces = IsolatedWorkspaceFactory(project_root, output_dir)
    holdout_evaluator = HoldoutEvaluator(sandbox_timeout)
    runs: list[dict] = []
    effective_repository_modes = repository_modes or (repository_context_enabled,)
    effective_repository_modes = tuple(dict.fromkeys(bool(item) for item in effective_repository_modes))

    for case in cases:
        strategies = strategy_override or case.strategies
        for strategy in strategies:
            for repository_enabled in effective_repository_modes:
                variant = "repository" if repository_enabled else "legacy"
                for repetition in range(1, repeat + 1):
                    started = time.perf_counter()
                    workspace: Path | None = None
                    try:
                        workspace = workspaces.prepare(case, strategy, repetition, variant)
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
                            semantic_review_max_contracts=semantic_review_max_contracts,
                            review_model=(review_model_factory() if review_model_factory else None),
                            repository_context_enabled=repository_enabled,
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
                        trace_path = save_trace(
                            result,
                            trace_dir,
                            redaction_mode=trace_redaction_mode,
                        )
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
                                repository_enabled=repository_enabled,
                            )
                        )
                    except Exception as exc:
                        runs.append(
                            build_runner_error(
                                case,
                                strategy,
                                repetition,
                                exc,
                                started,
                                repository_enabled=repository_enabled,
                            )
                        )
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
        "schema_version": 4,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize_runs(runs),
        "runs": runs,
    }


def build_run_record(
    case,
    strategy,
    repetition,
    result,
    holdout,
    trace_path,
    workspace,
    duration,
    *,
    repository_enabled: bool = False,
):
    repair_input_tokens = sum(
        int((record.model_call or {}).get("input_tokens") or 0) for record in result.iterations
    )
    repair_output_tokens = sum(
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
    input_tokens = repair_input_tokens + review_input_tokens
    output_tokens = repair_output_tokens + review_output_tokens
    repair_model_seconds = sum(
        float((record.model_call or {}).get("duration_seconds") or 0.0)
        for record in result.iterations
    )
    review_model_seconds = sum(
        float(call.get("duration_seconds") or 0.0)
        for review in (result.reviews or [])
        for call in review.model_calls
    )
    repository_contexts = _repository_contexts(result)
    selected_paths = _selected_context_paths(result)
    context_quality = _context_quality(case, selected_paths)
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
        "variant": "repository" if repository_enabled else "legacy",
        "repository_context_enabled": repository_enabled,
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
        "repair_input_tokens": repair_input_tokens,
        "repair_output_tokens": repair_output_tokens,
        "review_input_tokens": review_input_tokens,
        "review_output_tokens": review_output_tokens,
        "repair_model_seconds": round(repair_model_seconds, 6),
        "review_model_seconds": round(review_model_seconds, 6),
        "review_prompt_chars": sum(len(review.prompt) for review in (result.reviews or [])),
        "review_count": len(result.reviews or []),
        "semantic_revisions_used": result.semantic_revisions_used,
        "failure_type": failure_type,
        "trace_path": str(trace_path),
        "workspace": str(workspace),
        "workspace_strategy": result.workspace_strategy,
        "final_patch_path": result.final_patch_path,
        "candidate_patch_path": result.candidate_patch_path,
        "repository_context_builds": len(repository_contexts),
        "repository_cache_hits": sum(bool(item.get("cache_hit")) for item in repository_contexts),
        "repository_index_seconds": round(
            sum(float(item.get("total_seconds") or 0.0) for item in repository_contexts), 6
        ),
        "repository_build_seconds": round(
            sum(float(item.get("build_seconds") or 0.0) for item in repository_contexts), 6
        ),
        "repository_budget_truncations": sum(
            bool(item.get("budget_truncated")) for item in repository_contexts
        ),
        "repository_related_file_count": sum(
            int(item.get("related_file_count") or 0) for item in repository_contexts
        ),
        "repository_max_estimated_tokens": max(
            (int(item.get("estimated_selected_tokens") or 0) for item in repository_contexts),
            default=0,
        ),
        "selected_context_paths": sorted(selected_paths),
        **context_quality,
    }


def build_runner_error(
    case,
    strategy,
    repetition,
    exc,
    started,
    *,
    repository_enabled: bool = False,
):
    return {
        "case_id": case.case_id,
        "strategy": strategy,
        "variant": "repository" if repository_enabled else "legacy",
        "repository_context_enabled": repository_enabled,
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


def _repository_contexts(result) -> list[dict]:
    contexts: list[dict] = []
    for record in result.iterations:
        repository = (record.context or {}).get("repository")
        if repository:
            contexts.append(repository)
    for review in result.reviews or []:
        repository = (review.context or {}).get("repository")
        if repository:
            contexts.append(repository)
    return contexts


def _selected_context_paths(result) -> set[str]:
    paths: set[str] = set()
    for record in result.iterations:
        for item in (record.context or {}).get("selected_files", []):
            if item.get("path"):
                paths.add(str(item["path"]).replace("\\", "/"))
    return paths


def _context_quality(case, selected_paths: set[str]) -> dict:
    required = set(case.context_required_paths)
    relevant = set(case.context_relevant_paths)
    distractors = set(case.context_distractor_paths)
    required_hits = len(required & selected_paths)
    relevant_hits = len(relevant & selected_paths)
    distractor_hits = len(distractors & selected_paths)
    return {
        "context_required_count": len(required),
        "context_required_hits": required_hits,
        "context_required_recall": round(required_hits / len(required), 4) if required else None,
        "context_relevant_count": len(relevant),
        "context_relevant_hits": relevant_hits,
        "context_precision": round(relevant_hits / len(selected_paths), 4)
        if relevant and selected_paths
        else None,
        "context_distractor_count": len(distractors),
        "context_distractor_hits": distractor_hits,
        "context_distractor_rate": round(distractor_hits / len(distractors), 4)
        if distractors
        else None,
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
