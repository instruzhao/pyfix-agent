from __future__ import annotations

from dataclasses import dataclass
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
from pyfixagent.sandbox.base import Sandbox
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.utils.logger import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class BenchmarkOptions:
    project_root: Path
    output_dir: Path
    repeat: int = 5
    strategy_override: tuple[str, ...] = ()
    keep_workspaces: bool = False
    sandbox_timeout: int = 30
    context_line_window: int = 25
    context_max_files: int = 6
    context_max_expansion_level: int = 2
    max_changed_files: int = 8
    max_changed_lines: int = 400
    test_commands: tuple[tuple[str, ...], ...] | None = None
    semantic_review_enabled: bool = False
    semantic_review_max_revisions: int = 1
    semantic_review_parse_retries: int = 1
    semantic_review_max_context_chars: int = 16000
    semantic_review_max_feedback_chars: int = 3000
    semantic_review_max_risks: int = 5
    semantic_review_max_contracts: int = 3
    repository_context_enabled: bool = False
    repository_modes: tuple[bool, ...] | None = None
    repository_max_files: int = 2000
    repository_max_file_bytes: int = 1_000_000
    repository_max_graph_depth: int = 2
    repository_max_related_files: int = 6
    repository_max_snippet_lines: int = 200
    context_max_selected_tokens: int = 12000
    trace_redaction_mode: str = "paths"
    protocol_metadata: dict | None = None


@dataclass(frozen=True)
class BenchmarkVariant:
    case: BenchmarkCase
    strategy: str
    repetition: int
    repository_enabled: bool

    @property
    def label(self) -> str:
        return "repository" if self.repository_enabled else "legacy"


class BenchmarkRunner:
    """Coordinates isolated benchmark trials without owning their policy logic."""

    def __init__(
        self,
        options: BenchmarkOptions,
        model_factory: Callable[[], BaseModel],
        review_model_factory: Callable[[], BaseModel] | None,
        sandbox_factory: Callable[[Path], Sandbox] | None,
    ):
        if options.repeat < 1:
            raise ValueError("repeat must be at least 1")
        self.options = options
        self.model_factory = model_factory
        self.review_model_factory = review_model_factory
        self.output_dir = options.output_dir.resolve()
        self.trace_dir = self.output_dir / "traces"
        self.workspaces = IsolatedWorkspaceFactory(options.project_root, self.output_dir)
        self.sandbox_factory = sandbox_factory or (
            lambda workspace: LocalSandbox(workspace, timeout_seconds=options.sandbox_timeout)
        )
        self.holdout_evaluator = HoldoutEvaluator(
            options.sandbox_timeout,
            sandbox_factory=self.sandbox_factory,
        )
        configured_modes = options.repository_modes or (options.repository_context_enabled,)
        self.repository_modes = tuple(dict.fromkeys(bool(item) for item in configured_modes))

    def run(self, cases: list[BenchmarkCase]) -> dict:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        runs = [self._run_variant(variant) for variant in self._variants(cases)]
        return {
            "schema_version": 5,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "protocol": self.options.protocol_metadata or {"protocol_version": 1, "source": "library"},
            "summary": summarize_runs(runs),
            "runs": runs,
        }

    def _variants(self, cases: list[BenchmarkCase]):
        for case in cases:
            for strategy in self.options.strategy_override or case.strategies:
                for repository_enabled in self.repository_modes:
                    for repetition in range(1, self.options.repeat + 1):
                        yield BenchmarkVariant(case, strategy, repetition, repository_enabled)

    def _run_variant(self, variant: BenchmarkVariant) -> dict:
        started = time.perf_counter()
        workspace: Path | None = None
        try:
            workspace = self.workspaces.prepare(
                variant.case,
                variant.strategy,
                variant.repetition,
                variant.label,
            )
            record = self._run_prepared_workspace(variant, workspace, started)
        except Exception as exc:
            # A benchmark must retain an unexpected trial failure as evidence instead of aborting the run.
            logger.exception(
                "benchmark trial failed: case=%s strategy=%s repetition=%s variant=%s",
                variant.case.case_id,
                variant.strategy,
                variant.repetition,
                variant.label,
            )
            record = build_runner_error(
                variant.case,
                variant.strategy,
                variant.repetition,
                exc,
                started,
                repository_enabled=variant.repository_enabled,
            )
        return self._cleanup_variant(variant, workspace, record)

    def _run_prepared_workspace(
        self,
        variant: BenchmarkVariant,
        workspace: Path,
        started: float,
    ) -> dict:
        result = self._build_agent(variant, workspace).run(variant.case.agent_task)
        candidate_patch = result.candidate_patch or result.patch
        if result.visible_success and candidate_patch:
            _apply_exported_patch(workspace, candidate_patch)
        holdout = self.holdout_evaluator.run(variant.case, workspace)
        trace_path = save_trace(result, self.trace_dir, redaction_mode=self.options.trace_redaction_mode)
        return build_run_record(
            variant.case,
            variant.strategy,
            variant.repetition,
            result,
            holdout,
            trace_path,
            workspace,
            time.perf_counter() - started,
            repository_enabled=variant.repository_enabled,
        )

    def _build_agent(self, variant: BenchmarkVariant, workspace: Path) -> DefaultAgent:
        options = self.options
        return DefaultAgent(
            model=self.model_factory(),
            sandbox=self.sandbox_factory(workspace),
            patch_output_dir=self.output_dir / "patches",
            max_iterations=variant.case.max_iterations,
            initial_mode=variant.case.mode,
            context_strategy=variant.strategy,
            context_line_window=options.context_line_window,
            context_max_files=options.context_max_files,
            context_max_expansion_level=options.context_max_expansion_level,
            require_clean_workspace=True,
            allowed_paths=variant.case.allowed_paths,
            max_changed_files=options.max_changed_files,
            max_changed_lines=options.max_changed_lines,
            isolate_workspace=True,
            test_commands=options.test_commands,
            semantic_review_enabled=options.semantic_review_enabled,
            semantic_review_max_revisions=options.semantic_review_max_revisions,
            semantic_review_parse_retries=options.semantic_review_parse_retries,
            semantic_review_max_context_chars=options.semantic_review_max_context_chars,
            semantic_review_max_feedback_chars=options.semantic_review_max_feedback_chars,
            semantic_review_max_risks=options.semantic_review_max_risks,
            semantic_review_max_contracts=options.semantic_review_max_contracts,
            review_model=(self.review_model_factory() if self.review_model_factory else None),
            repository_context_enabled=variant.repository_enabled,
            repository_cache_dir=self.output_dir / "index",
            repository_max_files=options.repository_max_files,
            repository_max_file_bytes=options.repository_max_file_bytes,
            repository_max_graph_depth=options.repository_max_graph_depth,
            repository_max_related_files=options.repository_max_related_files,
            repository_max_snippet_lines=options.repository_max_snippet_lines,
            context_max_selected_tokens=options.context_max_selected_tokens,
        )

    def _cleanup_variant(
        self,
        variant: BenchmarkVariant,
        workspace: Path | None,
        record: dict,
    ) -> dict:
        if self.options.keep_workspaces or workspace is None:
            return record
        cleanup_error = self.workspaces.cleanup(variant.case, workspace)
        if not cleanup_error:
            return record
        record["success"] = False
        record["failure_type"] = "cleanup_error"
        record["cleanup_error"] = cleanup_error
        record["error"] = "; ".join(item for item in (record.get("error"), cleanup_error) if item)
        return record


def run_benchmark(
    *,
    cases: list[BenchmarkCase],
    project_root: Path,
    output_dir: Path,
    model_factory: Callable[[], BaseModel],
    review_model_factory: Callable[[], BaseModel] | None = None,
    sandbox_factory: Callable[[Path], Sandbox] | None = None,
    **option_overrides,
) -> dict:
    options = BenchmarkOptions(project_root, output_dir, **option_overrides)
    return BenchmarkRunner(options, model_factory, review_model_factory, sandbox_factory).run(cases)


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
    repository_contexts = _repository_contexts(result)
    selected_paths = _selected_context_paths(result)
    record = _run_identity(case, strategy, repetition, repository_enabled)
    record.update(_run_outcome(result, holdout))
    record.update(_run_iteration_metrics(result, duration))
    record.update(_run_model_metrics(result))
    record.update(_run_paths(result, trace_path, workspace))
    record.update(_repository_metrics(repository_contexts))
    record.update(_context_quality(case, selected_paths))
    record["selected_context_paths"] = sorted(selected_paths)
    return record


def _run_identity(case, strategy, repetition, repository_enabled: bool) -> dict:
    return {
        "case_id": case.case_id,
        "strategy": strategy,
        "variant": "repository" if repository_enabled else "legacy",
        "repository_context_enabled": repository_enabled,
        "repetition": repetition,
    }


def _run_outcome(result, holdout: dict) -> dict:
    visible_success = bool(result.visible_success)
    holdout_success = holdout.get("success")
    last_result = result.iterations[-1].iteration_result if result.iterations else None
    failure_type = _failure_type(result, visible_success, holdout_success, last_result)
    return {
        "success": bool(result.success) and holdout_success is not False,
        "candidate_success": visible_success and holdout_success is not False,
        "visible_success": visible_success,
        "agent_accepted": bool(result.success),
        "acceptance_status": result.acceptance_status,
        "holdout_success": holdout_success,
        "holdout_exit_code": holdout.get("exit_code"),
        "holdout_output": holdout.get("output", ""),
        "error": result.error,
        "failure_type": failure_type,
    }


def _failure_type(result, visible_success: bool, holdout_success, last_result: dict | None):
    if result.success and result.acceptance_status in {"accepted", "accepted_with_warnings"}:
        return "false_accept" if holdout_success is False else (last_result or {}).get("failure_type")
    if not result.success and visible_success and holdout_success is True:
        return "false_reject"
    if visible_success and holdout_success is False:
        return "semantic_rejected" if result.acceptance_status == "rejected" else "holdout_failed"
    return (last_result or {}).get("failure_type")


def _run_iteration_metrics(result, duration: float) -> dict:
    return {
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
    }


def _run_model_metrics(result) -> dict:
    repair_calls = [record.model_call or {} for record in result.iterations]
    review_calls = [call for review in (result.reviews or []) for call in review.model_calls]
    repair_input = _sum_model_metric(repair_calls, "input_tokens", int)
    repair_output = _sum_model_metric(repair_calls, "output_tokens", int)
    review_input = _sum_model_metric(review_calls, "input_tokens", int)
    review_output = _sum_model_metric(review_calls, "output_tokens", int)
    return {
        "input_tokens": repair_input + review_input,
        "output_tokens": repair_output + review_output,
        "repair_input_tokens": repair_input,
        "repair_output_tokens": repair_output,
        "review_input_tokens": review_input,
        "review_output_tokens": review_output,
        "repair_model_seconds": round(_sum_model_metric(repair_calls, "duration_seconds", float), 6),
        "review_model_seconds": round(_sum_model_metric(review_calls, "duration_seconds", float), 6),
        "review_prompt_chars": sum(len(review.prompt) for review in (result.reviews or [])),
        "review_count": len(result.reviews or []),
        "semantic_revisions_used": result.semantic_revisions_used,
    }


def _sum_model_metric(calls: list[dict], key: str, cast) -> int | float:
    return sum(cast(call.get(key) or 0) for call in calls)


def _run_paths(result, trace_path, workspace) -> dict:
    return {
        "trace_path": str(trace_path),
        "workspace": str(workspace),
        "workspace_strategy": result.workspace_strategy,
        "final_patch_path": result.final_patch_path,
        "candidate_patch_path": result.candidate_patch_path,
    }


def _repository_metrics(repository_contexts: list[dict]) -> dict:
    return {
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
        **_run_identity(case, strategy, repetition, repository_enabled),
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
