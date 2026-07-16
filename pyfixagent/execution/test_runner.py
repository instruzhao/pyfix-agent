from dataclasses import dataclass
from pathlib import Path
import tempfile

from pyfixagent.execution.test_policy import TestCommandPolicy
from pyfixagent.sandbox.local_sandbox import CommandResult, LocalSandbox


@dataclass(frozen=True)
class TestExecution:
    exit_code: int
    output: str
    command_result: CommandResult
    command_results: tuple[CommandResult, ...] = ()

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class TestRunner:
    """Runs and formats the project's visible pytest suite."""

    def __init__(
        self,
        sandbox: LocalSandbox,
        commands: tuple[tuple[str, ...], ...] | None = None,
        policy: TestCommandPolicy | None = None,
    ):
        self.sandbox = sandbox
        self.policy = policy or TestCommandPolicy()
        raw_commands = commands or (("python", "-m", "pytest", "-p", "no:cacheprovider"),)
        self.commands = tuple(self.policy.validate(command) for command in raw_commands)

    def run(self, workspace: Path | None = None) -> TestExecution:
        sandbox = self.sandbox
        if workspace is not None and Path(workspace).resolve() != sandbox.workspace.resolve():
            sandbox = LocalSandbox(Path(workspace), timeout_seconds=sandbox.timeout_seconds)
        results: list[CommandResult] = []
        with tempfile.TemporaryDirectory(
            prefix="pyfixagent-pytest-",
            ignore_cleanup_errors=True,
        ) as temporary_root:
            for index, command in enumerate(self.commands, start=1):
                effective_command = self._with_isolated_basetemp(
                    command,
                    Path(temporary_root) / f"command-{index}",
                )
                result = sandbox.run(list(effective_command))
                results.append(result)
                if result.exit_code != 0:
                    break
        result = results[-1]
        return TestExecution(
            exit_code=result.exit_code,
            output="\n\n".join(self.format_output(item) for item in results),
            command_result=result,
            command_results=tuple(results),
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

    @staticmethod
    def _with_isolated_basetemp(command: tuple[str, ...], basetemp: Path) -> tuple[str, ...]:
        if any(part == "--basetemp" or part.startswith("--basetemp=") for part in command):
            return command
        return (*command, f"--basetemp={basetemp}")
