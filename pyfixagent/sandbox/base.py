from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass
class CommandResult:
    command: list[str]
    exit_code: int
    stdout: str
    stderr: str
    duration: float
    timeout: bool = False
    backend: str = "local"
    runtime_command: list[str] = field(default_factory=list)
    infrastructure_error: bool = False
    output_truncated: bool = False
    policy_violation: str | None = None


class Sandbox(Protocol):
    """Execution boundary used by visible tests and holdout evaluation."""

    workspace: Path
    timeout_seconds: int
    backend: str

    def run(self, command: list[str], timeout: int | None = None) -> CommandResult: ...

    def with_workspace(self, workspace: Path) -> "Sandbox": ...

    def pytest_basetemp(self, host_root: Path, index: int) -> str: ...

    def environment_metadata(self) -> dict: ...
