from dataclasses import dataclass
from pathlib import Path


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
