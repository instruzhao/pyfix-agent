from dataclasses import dataclass

from pyfixagent.sandbox.local_sandbox import CommandResult, LocalSandbox
from pyfixagent.tools.shell_tools import run_pytest


@dataclass(frozen=True)
class TestExecution:
    exit_code: int
    output: str
    command_result: CommandResult

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class TestRunner:
    """Runs and formats the project's visible pytest suite."""

    def __init__(self, sandbox: LocalSandbox):
        self.sandbox = sandbox

    def run(self) -> TestExecution:
        result = run_pytest(self.sandbox)
        return TestExecution(
            exit_code=result.exit_code,
            output=self.format_output(result),
            command_result=result,
        )

    @staticmethod
    def format_output(result: CommandResult) -> str:
        parts = [
            f"command: {' '.join(result.command)}",
            f"exit_code: {result.exit_code}",
            f"duration: {result.duration:.2f}s",
            f"timeout: {result.timeout}",
            "stdout:",
            result.stdout,
            "stderr:",
            result.stderr,
        ]
        return "\n".join(parts)
