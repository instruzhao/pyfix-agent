from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
from typing import Callable

from pyfixagent.benchmarking.contracts import BenchmarkCase
from pyfixagent.sandbox.base import Sandbox
from pyfixagent.sandbox.local_sandbox import LocalSandbox


class IsolatedWorkspaceFactory:
    """Creates and cleans independent Git baselines for benchmark runs."""

    def __init__(self, project_root: Path, output_dir: Path):
        self.project_root = Path(project_root)
        self.output_dir = Path(output_dir).resolve()

    def prepare(
        self,
        case: BenchmarkCase,
        strategy: str,
        repetition: int,
        variant: str = "default",
    ) -> Path:
        if case.fixture is None:
            if case.workspace is None:
                raise ValueError(f"case {case.case_id} has no fixture or workspace")
            self._run_reset(case)
            return case.workspace

        workspace = (
            self.output_dir
            / "workspaces"
            / case.case_id
            / strategy
            / variant
            / f"run_{repetition}"
        )
        self._safe_remove(workspace)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(
            case.fixture,
            workspace,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
        )
        try:
            self._run_checked(["git", "init"], workspace)
            self._run_checked(["git", "config", "user.email", "benchmark@pyfixagent.local"], workspace)
            self._run_checked(["git", "config", "user.name", "PyFixAgent Benchmark"], workspace)
            self._run_checked(["git", "add", "."], workspace)
            self._run_checked(["git", "commit", "-m", "benchmark: failing baseline"], workspace)
        except Exception:
            self._safe_remove(workspace)
            raise
        return workspace

    def cleanup(self, case: BenchmarkCase, workspace: Path) -> str | None:
        try:
            if case.fixture is not None:
                self._safe_remove(workspace)
            else:
                self._run_reset(case)
            return None
        except Exception as exc:
            return str(exc)

    def _run_reset(self, case: BenchmarkCase) -> None:
        completed = subprocess.run(
            list(case.reset_command),
            cwd=self.project_root,
            timeout=60,
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(f"reset failed for {case.case_id}: {message}")

    @staticmethod
    def _run_checked(command: list[str], cwd: Path) -> None:
        completed = subprocess.run(command, cwd=cwd, timeout=30, capture_output=True, text=True, check=False)
        if completed.returncode != 0:
            raise RuntimeError(f"command failed: {' '.join(command)}: {completed.stderr.strip()}")

    def _safe_remove(self, path: Path) -> None:
        resolved = path.resolve()
        try:
            resolved.relative_to(self.output_dir)
        except ValueError as exc:
            raise RuntimeError(f"refusing to remove benchmark path outside output directory: {path}") from exc
        if resolved.exists():
            shutil.rmtree(resolved, onerror=self._remove_readonly)

    @staticmethod
    def _remove_readonly(function, path, _exc_info) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)


class HoldoutEvaluator:
    """Runs external tests that are never included in the agent context."""

    def __init__(
        self,
        timeout: int,
        sandbox_factory: Callable[[Path], Sandbox] | None = None,
    ):
        self.timeout = timeout
        self.sandbox_factory = sandbox_factory or (
            lambda workspace: LocalSandbox(workspace, timeout_seconds=timeout)
        )

    def run(self, case: BenchmarkCase, workspace: Path) -> dict:
        if case.holdout_path is None:
            return {"evaluated": False, "success": None, "exit_code": None, "output": ""}
        workspace = Path(workspace).resolve()
        temporary_root = Path(
            tempfile.mkdtemp(prefix=".pyfixagent-holdout-", dir=workspace)
        ).resolve()
        try:
            source = Path(case.holdout_path)
            target = temporary_root / source.name
            if source.is_dir():
                shutil.copytree(
                    source,
                    target,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache"),
                )
            else:
                shutil.copy2(source, target)
            sandbox = self.sandbox_factory(workspace)
            relative_target = target.relative_to(workspace).as_posix()
            command = [
                "python",
                "-m",
                "pytest",
                "-q",
                "-p",
                "no:cacheprovider",
                f"--basetemp={sandbox.pytest_basetemp(temporary_root, 0)}",
                relative_target,
            ]
            completed = sandbox.run(command, timeout=self.timeout)
            return {
                "evaluated": True,
                "success": completed.exit_code == 0,
                "exit_code": completed.exit_code,
                "output": (completed.stdout + completed.stderr)[-8000:],
                "backend": completed.backend,
                "timeout": completed.timeout,
            }
        finally:
            if temporary_root.exists():
                shutil.rmtree(temporary_root, onerror=IsolatedWorkspaceFactory._remove_readonly)
