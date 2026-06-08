from dataclasses import dataclass
from pathlib import Path
import subprocess
import time

from pyfixagent.sandbox.policy import is_command_allowed


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    timeout: bool = False


class LocalSandbox:
    def __init__(self, workspace: Path, timeout_seconds: int = 30):
        self.workspace = Path(workspace)
        self.timeout_seconds = timeout_seconds

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
            )

        try:
            completed = subprocess.run(
                command,
                cwd=self.workspace,
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
            )
        except subprocess.TimeoutExpired as exc:
            return CommandResult(
                command=command,
                exit_code=124,
                stdout=exc.stdout or "",
                stderr=exc.stderr or f"command timed out after {timeout_seconds}s",
                duration=time.perf_counter() - start,
                timeout=True,
            )
        except Exception as exc:
            return CommandResult(
                command=command,
                exit_code=1,
                stdout="",
                stderr=f"failed to run command: {exc}",
                duration=time.perf_counter() - start,
                timeout=False,
            )
