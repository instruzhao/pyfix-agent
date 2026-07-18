import os
from pathlib import Path
import shutil
import subprocess
import time

from pyfixagent.sandbox.base import CommandResult
from pyfixagent.sandbox.policy import is_command_allowed


class LocalSandbox:
    backend = "local"

    def __init__(self, workspace: Path, timeout_seconds: int = 30):
        self.workspace = Path(workspace)
        self.timeout_seconds = timeout_seconds

    def with_workspace(self, workspace: Path) -> "LocalSandbox":
        return LocalSandbox(Path(workspace), timeout_seconds=self.timeout_seconds)

    def pytest_basetemp(self, host_root: Path, index: int) -> str:
        return str(Path(host_root) / f"command-{index}")

    def environment_metadata(self) -> dict:
        return {
            "backend": self.backend,
            "isolation": "host_process",
            "timeout_seconds": self.timeout_seconds,
            "network": "host",
            "filesystem": "host",
            "dependency_policy": "host_environment",
        }

    def run(self, command: list[str], timeout: int | None = None) -> CommandResult:
        start = time.perf_counter()
        timeout_seconds = timeout or self.timeout_seconds

        allowed, reason = is_command_allowed(command)
        if not allowed:
            return CommandResult(
                command=command,
                exit_code=126,
                stdout="",
                stderr=reason or "command is not allowed",
                duration=time.perf_counter() - start,
                timeout=False,
                backend=self.backend,
                infrastructure_error=True,
            )

        try:
            if _is_python_command(command):
                _clean_python_bytecode_cache(self.workspace)
            env = os.environ.copy()
            env["PYTHONDONTWRITEBYTECODE"] = "1"
            completed = subprocess.run(
                command,
                cwd=self.workspace,
                env=env,
                timeout=timeout_seconds,
                capture_output=True,
                text=True,
                check=False,
            )
            return CommandResult(
                command=command,
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration=time.perf_counter() - start,
                timeout=False,
                backend=self.backend,
                runtime_command=list(command),
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=command,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or f"command timed out after {timeout_seconds}s",
                duration=time.perf_counter() - start,
                timeout=True,
                backend=self.backend,
                runtime_command=list(command),
            )
        except Exception as exc:
            return CommandResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"failed to run command: {exc}",
                duration=time.perf_counter() - start,
                timeout=False,
                backend=self.backend,
                runtime_command=list(command),
                infrastructure_error=True,
            )


def _is_python_command(command: list[str]) -> bool:
    if not command:
        return False
    executable = Path(command[0]).name.lower()
    return executable == "python" or executable.startswith("python.")


def _clean_python_bytecode_cache(workspace: Path) -> None:
    workspace_path = Path(workspace).resolve()
    if not workspace_path.exists():
        return

    for cache_dir in workspace_path.rglob("__pycache__"):
        resolved = cache_dir.resolve()
        try:
            resolved.relative_to(workspace_path)
        except ValueError:
            continue
        if resolved.is_dir():
            shutil.rmtree(resolved)
