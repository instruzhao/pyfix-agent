from dataclasses import dataclass, field
from pathlib import Path

from pyfixagent.schemas import IterationRecord, ReviewRecord


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
    visible_success: bool = False
    acceptance_status: str = "not_run"
    candidate_patch: str = ""
    candidate_patch_path: str = ""
    reviews: list[ReviewRecord] = field(default_factory=list)
    semantic_revisions_used: int = 0
    error: str | None = None
    workspace_state: dict | None = None
    workspace_strategy: str = "in_place"
    final_patch_path: str = ""
