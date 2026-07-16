from dataclasses import dataclass, field
from pathlib import Path

from pyfixagent.schemas import IterationRecord


@dataclass
class AgentState:
    task: str
    workspace: Path
    original_workspace: Path | None = None
    file_tree: str = ""
    test_output_before: str = ""
    test_output_after: str = ""
    patch: str = ""
    changed_files: list[str] = field(default_factory=list)
    iterations: list[IterationRecord] = field(default_factory=list)
    success: bool = False
    error: str | None = None
    workspace_state: dict | None = None
    workspace_strategy: str = "in_place"
    final_patch_path: str = ""
