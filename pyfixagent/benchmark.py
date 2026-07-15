from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import time
from typing import Callable

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.main import build_litellm_model_name, load_dotenv_file, save_trace
from pyfixagent.models.base import BaseModel
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.utils.config import load_config


@dataclass(frozen=True)
class BenchmarkCase:
    case_id: str
    allowed_paths: tuple[str, ...]
    strategies: tuple[str, ...] = ("traceback",)
    mode: str = "replacement"
    max_iterations: int = 5
    fixture: Path | None = None
    holdout_path: Path | None = None
    workspace: Path | None = None
    reset_command: tuple[str, ...] = ()
    task: str | None = None

    @property
    def agent_task(self) -> str:
        return self.task or build_generic_task(self.allowed_paths)


def build_generic_task(allowed_paths: tuple[str, ...]) -> str:
    if allowed_paths:
        roots = ", ".join(f"{path}/" for path in allowed_paths)
        scope = f"Only modify Python files under {roots}. "
    else:
        scope = "Only modify Python source files. "
    return f"Fix all failing tests. {scope}Do not modify tests/."


def load_manifest(path: str | Path, project_root: str | Path) -> list[BenchmarkCase]:
    root = Path(project_root).resolve()
    data = load_config(Path(path))
    schema_version = data.get("schema_version")
    if schema_version not in {1, 2}:
        raise ValueError("benchmark manifest schema_version must be 1 or 2")
    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("benchmark manifest must contain a non-empty cases list")

    cases: list[BenchmarkCase] = []
    seen: set[str] = set()
    for raw in raw_cases:
        if not isinstance(raw, dict):
            raise ValueError("each benchmark case must be a mapping")
        case_id = str(raw.get("id", "")).strip()
        if not case_id or case_id in seen:
            raise ValueError(f"benchmark case id is empty or duplicated: {case_id!r}")
        seen.add(case_id)
        strategies = tuple(raw.get("strategies") or ["traceback"])
        if any(item not in {"traceback", "full"} for item in strategies):
            raise ValueError(f"case {case_id} contains an unsupported context strategy")
        mode = str(raw.get("mode", "replacement"))
        if mode not in {"replacement", "patch"}:
            raise ValueError(f"case {case_id} contains an unsupported mode")
        allowed_paths = tuple(str(item).strip("/\\") for item in raw.get("allowed_paths", []))

        if schema_version == 2:
            if "task" in raw:
                raise ValueError(f"case {case_id} must not contain task hints in schema v2")
            fixture = _existing_directory(root, raw.get("fixture"), f"case {case_id} fixture")
            holdout = _existing_directory(root, raw.get("holdout"), f"case {case_id} holdout")
            cases.append(
                BenchmarkCase(
                    case_id=case_id,
                    allowed_paths=allowed_paths,
                    strategies=strategies,
                    mode=mode,
                    max_iterations=max(1, int(raw.get("max_iterations", 5))),
                    fixture=fixture,
                    holdout_path=holdout,
                )
            )
            continue

        workspace = _inside_root(root, root / str(raw.get("workspace", "")))
        reset = raw.get("reset_command")
        if not isinstance(reset, list) or not reset or not all(isinstance(item, str) for item in reset):
            raise ValueError(f"case {case_id} reset_command must be a non-empty string list")
        cases.append(
            BenchmarkCase(
                case_id=case_id,
                allowed_paths=allowed_paths,
                strategies=strategies,
                mode=mode,
                max_iterations=max(1, int(raw.get("max_iterations", 3))),
                workspace=workspace,
                reset_command=tuple(reset),
                task=str(raw.get("task", "Fix the failing tests.")),
            )
        )
    return cases


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
    max_changed_files: int = 8,
    max_changed_lines: int = 400,
) -> dict:
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    trace_dir = output_dir / "traces"
    runs: list[dict] = []

    for case in cases:
        strategies = strategy_override or case.strategies
        for strategy in strategies:
            for repetition in range(1, repeat + 1):
                started = time.perf_counter()
                workspace: Path | None = None
                try:
                    workspace = _prepare_workspace(case, output_dir, strategy, repetition, project_root)
                    model = model_factory()
                    agent = DefaultAgent(
                        model=model,
                        sandbox=LocalSandbox(workspace, timeout_seconds=sandbox_timeout),
                        patch_output_dir=output_dir / "patches",
                        max_iterations=case.max_iterations,
                        initial_mode=case.mode,
                        context_strategy=strategy,
                        context_line_window=context_line_window,
                        context_max_files=context_max_files,
                        require_clean_workspace=True,
                        allowed_paths=case.allowed_paths,
                        max_changed_files=max_changed_files,
                        max_changed_lines=max_changed_lines,
                    )
                    result = agent.run(case.agent_task)
                    holdout = _run_holdout(case, workspace, sandbox_timeout)
                    trace_path = save_trace(result, trace_dir)
                    runs.append(
                        _run_record(
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
                    runs.append(_runner_error(case, strategy, repetition, exc, started))
                finally:
                    if not keep_workspaces and workspace is not None:
                        cleanup_error = _cleanup_workspace(case, workspace, project_root, output_dir)
                        if cleanup_error:
                            run = runs[-1]
                            run["success"] = False
                            run["failure_type"] = "cleanup_error"
                            run["cleanup_error"] = cleanup_error
                            run["error"] = "; ".join(
                                item for item in (run.get("error"), cleanup_error) if item
                            )

    return {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": summarize_runs(runs),
        "runs": runs,
    }


def summarize_runs(runs: list[dict]) -> dict:
    total = len(runs)
    successes = sum(bool(run.get("success")) for run in runs)
    visible_successes = sum(bool(run.get("visible_success")) for run in runs)
    holdout_evaluated = [run for run in runs if run.get("holdout_success") is not None]
    holdout_successes = sum(bool(run.get("holdout_success")) for run in holdout_evaluated)
    case_keys = {(run.get("case_id"), run.get("strategy")) for run in runs}
    passed_cases = sum(
        any(run.get("success") for run in runs if (run.get("case_id"), run.get("strategy")) == key)
        for key in case_keys
    )
    first_runs = [run for run in runs if int(run.get("repetition", 1)) == 1]
    failure_counts = Counter(
        str(run.get("failure_type") or "unknown") for run in runs if not run.get("success")
    )
    iteration_results = [
        failure_type
        for run in runs
        for failure_type in (run.get("iteration_failure_types") or [])
    ]
    return {
        "runs": total,
        "successful_runs": successes,
        "success_rate": _rate(successes, total),
        "visible_success_rate": _rate(visible_successes, total),
        "holdout_success_rate": _rate(holdout_successes, len(holdout_evaluated)),
        "case_strategy_pairs": len(case_keys),
        "pass_at_k": _rate(passed_cases, len(case_keys)),
        "success_at_1": _rate(sum(bool(run.get("success")) for run in first_runs), len(first_runs)),
        "average_iterations": round(
            sum(int(run.get("iterations", 0)) for run in runs) / total, 3
        ) if total else 0.0,
        "regression_rate": _rate(iteration_results.count("regression"), len(iteration_results)),
        "no_progress_rate": _rate(iteration_results.count("no_progress"), len(iteration_results)),
        "failure_counts": dict(sorted(failure_counts.items())),
        "policy_violation_count": sum(int(run.get("policy_violation_count", 0)) for run in runs),
        "total_prompt_chars": sum(int(run.get("prompt_chars", 0)) for run in runs),
        "total_input_tokens": sum(int(run.get("input_tokens", 0)) for run in runs),
        "total_output_tokens": sum(int(run.get("output_tokens", 0)) for run in runs),
    }


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# PyFixAgent Benchmark Report",
        "",
        f"- Runs: {summary['runs']}",
        f"- Final success rate: {summary['success_rate']:.1%}",
        f"- Visible-test success rate: {summary['visible_success_rate']:.1%}",
        f"- Holdout success rate: {summary['holdout_success_rate']:.1%}",
        f"- Success@1: {summary['success_at_1']:.1%}",
        f"- Pass@k: {summary['pass_at_k']:.1%}",
        f"- Average iterations: {summary['average_iterations']}",
        f"- Regression rate: {summary['regression_rate']:.1%}",
        "",
        "| Case | Strategy | Repeat | Visible | Holdout | Final | Iterations | Failure type | Tokens |",
        "|---|---|---:|---|---|---|---:|---|---:|",
    ]
    for run in report["runs"]:
        lines.append(
            f"| {run['case_id']} | {run['strategy']} | {run['repetition']} | "
            f"{_yes_no(run.get('visible_success'))} | {_yes_no(run.get('holdout_success'))} | "
            f"{_yes_no(run.get('success'))} | {run['iterations']} | "
            f"{run.get('failure_type') or ''} | "
            f"{int(run.get('input_tokens', 0)) + int(run.get('output_tokens', 0))} |"
        )
    return "\n".join(lines) + "\n"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated PyFixAgent benchmark cases.")
    parser.add_argument("--manifest", default="benchmarks/cases.yaml")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--strategy", action="append", choices=["traceback", "full"], dest="strategies")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output-dir", default="outputs/benchmarks")
    parser.add_argument("--list", action="store_true", dest="list_cases")
    parser.add_argument("--validate", action="store_true", dest="validate_cases")
    parser.add_argument("--keep-workspaces", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[1]
    cases = load_manifest(_resolve(project_root, args.manifest), project_root)
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.case_id in selected]
        missing = selected - {case.case_id for case in cases}
        if missing:
            raise ValueError(f"unknown benchmark cases: {', '.join(sorted(missing))}")
    if args.list_cases:
        for case in cases:
            source = case.fixture or case.workspace
            holdout = case.holdout_path or "none"
            print(f"{case.case_id}\t{source}\tholdout={holdout}")
        return 0
    if args.validate_cases:
        results = validate_benchmark_cases(cases)
        for result in results:
            print(f"{result['case_id']}\t{'ok' if result['valid'] else 'invalid'}\t{result['reason']}")
        return 0 if all(result["valid"] for result in results) else 1

    load_dotenv_file(project_root / ".env")
    config = load_config(_resolve(project_root, args.config))
    model_config = config.get("model", {})

    def model_factory() -> BaseModel:
        api_key_env = model_config.get("api_key_env")
        return LiteLLMModel(
            model_name=build_litellm_model_name(model_config),
            api_base=model_config.get("api_base"),
            api_key=os.getenv(api_key_env) if api_key_env else None,
            temperature=float(model_config.get("temperature", 0.0)),
            max_tokens=int(model_config.get("max_tokens", 2000)),
            timeout_seconds=int(model_config.get("timeout_seconds", 60)),
            extra_body={"enable_thinking": bool(model_config.get("enable_thinking", False))},
        )

    output_dir = _resolve(project_root, args.output_dir)
    report = run_benchmark(
        cases=cases,
        project_root=project_root,
        output_dir=output_dir,
        model_factory=model_factory,
        repeat=args.repeat,
        strategy_override=tuple(args.strategies or ()),
        keep_workspaces=args.keep_workspaces,
        sandbox_timeout=int(config.get("sandbox", {}).get("timeout_seconds", 30)),
        context_line_window=int(config.get("context", {}).get("line_window", 25)),
        context_max_files=int(config.get("context", {}).get("max_files", 6)),
        max_changed_files=int(config.get("safety", {}).get("max_changed_files", 8)),
        max_changed_lines=int(config.get("safety", {}).get("max_changed_lines", 400)),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    return 0 if report["summary"]["success_rate"] == 1.0 else 1


def cli() -> None:
    raise SystemExit(main())


def _prepare_workspace(
    case: BenchmarkCase,
    output_dir: Path,
    strategy: str,
    repetition: int,
    project_root: Path,
) -> Path:
    if case.fixture is None:
        if case.workspace is None:
            raise ValueError(f"case {case.case_id} has no fixture or workspace")
        _run_reset(case, project_root)
        return case.workspace

    workspace = output_dir / "workspaces" / case.case_id / strategy / f"run_{repetition}"
    _safe_remove(workspace, output_dir)
    workspace.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(case.fixture, workspace)
    try:
        _run_checked(["git", "init"], workspace)
        _run_checked(["git", "config", "user.email", "benchmark@pyfixagent.local"], workspace)
        _run_checked(["git", "config", "user.name", "PyFixAgent Benchmark"], workspace)
        _run_checked(["git", "add", "."], workspace)
        _run_checked(["git", "commit", "-m", "benchmark: failing baseline"], workspace)
    except Exception:
        _safe_remove(workspace, output_dir)
        raise
    return workspace


def _run_holdout(case: BenchmarkCase, workspace: Path, timeout: int) -> dict:
    if case.holdout_path is None:
        return {"evaluated": False, "success": None, "exit_code": None, "output": ""}
    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPATH"] = os.pathsep.join(
        item for item in (str(workspace), env.get("PYTHONPATH", "")) if item
    )
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(case.holdout_path)],
        cwd=workspace,
        env=env,
        timeout=timeout,
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "evaluated": True,
        "success": completed.returncode == 0,
        "exit_code": completed.returncode,
        "output": (completed.stdout + completed.stderr)[-8000:],
    }


def _run_record(case, strategy, repetition, result, holdout, trace_path, workspace, duration):
    input_tokens = sum(int((record.model_call or {}).get("input_tokens") or 0) for record in result.iterations)
    output_tokens = sum(int((record.model_call or {}).get("output_tokens") or 0) for record in result.iterations)
    visible_success = bool(result.success)
    holdout_success = holdout.get("success")
    success = visible_success and holdout_success is not False
    last_result = result.iterations[-1].iteration_result if result.iterations else None
    if visible_success and holdout_success is False:
        failure_type = "holdout_failed"
    else:
        failure_type = (last_result or {}).get("failure_type") if last_result else None
    return {
        "case_id": case.case_id,
        "strategy": strategy,
        "repetition": repetition,
        "success": success,
        "visible_success": visible_success,
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
        "prompt_chars": sum(int((record.context or {}).get("stats", {}).get("prompt_chars") or 0) for record in result.iterations),
        "selected_context_chars": sum(int((record.context or {}).get("stats", {}).get("selected_context_chars") or 0) for record in result.iterations),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "failure_type": failure_type,
        "trace_path": str(trace_path),
        "workspace": str(workspace),
    }


def _runner_error(case, strategy, repetition, exc, started):
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


def _cleanup_workspace(case, workspace, project_root, output_dir) -> str | None:
    try:
        if case.fixture is not None:
            _safe_remove(workspace, output_dir)
        else:
            _run_reset(case, project_root)
        return None
    except Exception as exc:
        return str(exc)


def validate_benchmark_cases(cases: list[BenchmarkCase], timeout: int = 60) -> list[dict]:
    results: list[dict] = []
    for case in cases:
        reasons: list[str] = []
        if case.fixture is None:
            reasons.append("legacy workspace case is not isolated")
        else:
            for allowed_path in case.allowed_paths:
                if not (case.fixture / allowed_path).is_dir():
                    reasons.append(f"allowed path does not exist: {allowed_path}")
            if not (case.fixture / "tests").is_dir():
                reasons.append("visible tests directory is missing")
            if (case.fixture / ".git").exists():
                reasons.append("fixture must not contain a Git repository")
            if case.holdout_path is None:
                reasons.append("holdout tests are missing")
            elif _is_within(case.holdout_path, case.fixture):
                reasons.append("holdout tests must be outside the agent fixture")

            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            with tempfile.TemporaryDirectory(prefix=f"pyfixagent-{case.case_id}-") as temp_dir:
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pytest",
                        "-q",
                        "-p",
                        "no:cacheprovider",
                        f"--basetemp={temp_dir}",
                    ],
                    cwd=case.fixture,
                    env=env,
                    timeout=timeout,
                    capture_output=True,
                    text=True,
                    check=False,
                )
            if completed.returncode == 0:
                reasons.append("failing baseline unexpectedly passes visible tests")
            elif completed.returncode not in {1}:
                reasons.append(f"visible tests could not run (exit {completed.returncode})")
        results.append(
            {
                "case_id": case.case_id,
                "valid": not reasons,
                "reason": "; ".join(reasons) if reasons else "isolated failing baseline with external holdout",
            }
        )
    return results


def _run_reset(case: BenchmarkCase, project_root: Path) -> None:
    completed = subprocess.run(
        list(case.reset_command), cwd=project_root, timeout=60, capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise RuntimeError(f"reset failed for {case.case_id}: {completed.stderr.strip() or completed.stdout.strip()}")


def _run_checked(command: list[str], cwd: Path) -> None:
    completed = subprocess.run(command, cwd=cwd, timeout=30, capture_output=True, text=True, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed: {' '.join(command)}: {completed.stderr.strip()}")


def _safe_remove(path: Path, root: Path) -> None:
    resolved = path.resolve()
    try:
        resolved.relative_to(root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"refusing to remove benchmark path outside output directory: {path}") from exc
    if resolved.exists():
        shutil.rmtree(resolved, onerror=_remove_readonly)


def _remove_readonly(function, path, _exc_info) -> None:
    os.chmod(path, stat.S_IWRITE)
    function(path)


def _existing_directory(root: Path, value, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a project-relative directory")
    path = _inside_root(root, root / value)
    if not path.is_dir():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def _inside_root(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"benchmark path escapes project root: {path}") from exc
    return resolved


def _is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def _resolve(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _yes_no(value) -> str:
    if value is None:
        return "n/a"
    return "yes" if value else "no"


if __name__ == "__main__":
    cli()
