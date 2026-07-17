from __future__ import annotations

import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile

from pyfixagent.benchmarking.contracts import BenchmarkCase
from pyfixagent.benchmarking.paths import existing_directory, inside_root, is_within
from pyfixagent.utils.config import load_config


def load_manifest(path: str | Path, project_root: str | Path) -> list[BenchmarkCase]:
    root = Path(project_root).resolve()
    data = load_config(Path(path))
    schema_version = data.get("schema_version")
    if schema_version not in {1, 2, 3}:
        raise ValueError("benchmark manifest schema_version must be 1, 2, or 3")
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
        tags = _string_tuple(raw.get("tags", []), f"case {case_id} tags")
        required_paths = _path_tuple(
            raw.get("context_required_paths", []), f"case {case_id} context_required_paths"
        )
        relevant_paths = _path_tuple(
            raw.get("context_relevant_paths", []), f"case {case_id} context_relevant_paths"
        )
        distractor_paths = _path_tuple(
            raw.get("context_distractor_paths", []), f"case {case_id} context_distractor_paths"
        )
        if schema_version < 3 and (tags or required_paths or relevant_paths or distractor_paths):
            raise ValueError(f"case {case_id} context metadata requires manifest schema v3")
        if relevant_paths and not set(required_paths).issubset(relevant_paths):
            raise ValueError(f"case {case_id} required context paths must also be relevant")
        if set(relevant_paths) & set(distractor_paths):
            raise ValueError(f"case {case_id} context paths cannot be both relevant and distractors")

        if schema_version in {2, 3}:
            if "task" in raw:
                raise ValueError(f"case {case_id} must not contain task hints in schema v2+")
            cases.append(
                BenchmarkCase(
                    case_id=case_id,
                    allowed_paths=allowed_paths,
                    strategies=strategies,
                    mode=mode,
                    max_iterations=max(1, int(raw.get("max_iterations", 5))),
                    fixture=existing_directory(root, raw.get("fixture"), f"case {case_id} fixture"),
                    holdout_path=existing_directory(root, raw.get("holdout"), f"case {case_id} holdout"),
                    tags=tags,
                    context_required_paths=required_paths,
                    context_relevant_paths=relevant_paths,
                    context_distractor_paths=distractor_paths,
                )
            )
            continue

        workspace = inside_root(root, root / str(raw.get("workspace", "")))
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
            elif is_within(case.holdout_path, case.fixture):
                reasons.append("holdout tests must be outside the agent fixture")

            for expected in (
                *case.context_required_paths,
                *case.context_relevant_paths,
                *case.context_distractor_paths,
            ):
                candidate = case.fixture / expected
                if not is_within(candidate, case.fixture):
                    reasons.append(f"context expectation path escapes fixture: {expected}")
                elif not candidate.is_file():
                    reasons.append(f"context expectation path is missing: {expected}")

            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            with tempfile.TemporaryDirectory(prefix=f"pyfixagent-{case.case_id}-") as temp_dir:
                env["PYTHONPYCACHEPREFIX"] = str(Path(temp_dir) / "pycache")
                for hash_seed in ("0", "1"):
                    env["PYTHONHASHSEED"] = hash_seed
                    completed = subprocess.run(
                        [
                            sys.executable,
                            "-m",
                            "pytest",
                            "-q",
                            "-p",
                            "no:cacheprovider",
                            f"--basetemp={Path(temp_dir) / hash_seed}",
                        ],
                        cwd=case.fixture,
                        env=env,
                        timeout=timeout,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    if completed.returncode == 0:
                        reasons.append(
                            f"failing baseline unexpectedly passes visible tests with PYTHONHASHSEED={hash_seed}"
                        )
                    elif completed.returncode not in {1}:
                        reasons.append(
                            f"visible tests could not run with PYTHONHASHSEED={hash_seed} "
                            f"(exit {completed.returncode})"
                        )
        results.append(
            {
                "case_id": case.case_id,
                "valid": not reasons,
                "reason": "; ".join(reasons) if reasons else "isolated failing baseline with external holdout",
            }
        )
    return results


def _string_tuple(value, name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        if value == []:
            return ()
        raise ValueError(f"{name} must be a string list")
    return tuple(dict.fromkeys(item.strip() for item in value))


def _path_tuple(value, name: str) -> tuple[str, ...]:
    paths: list[str] = []
    for item in _string_tuple(value, name):
        normalized = item.replace("\\", "/").rstrip("/")
        posix_path = PurePosixPath(normalized)
        if (
            not normalized
            or posix_path.is_absolute()
            or Path(normalized).is_absolute()
            or ".." in posix_path.parts
        ):
            raise ValueError(f"{name} must contain workspace-relative paths")
        paths.append(normalized)
    return tuple(paths)
