from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pyfixagent.tools.file_tools import list_files
from pyfixagent.workspace import clean_workspace_error, inspect_workspace


@dataclass(frozen=True)
class PreparedWorkspace:
    file_tree: str
    state: dict
    error: str | None = None


class WorkspaceSession:
    """Owns run setup and generated artifact paths for one workspace."""

    def __init__(self, workspace: Path, patch_output_dir: Path, require_clean: bool = False):
        self.workspace = Path(workspace)
        self.patch_output_dir = Path(patch_output_dir)
        self.require_clean = require_clean

    def prepare(self) -> PreparedWorkspace:
        state = inspect_workspace(self.workspace)
        error = clean_workspace_error(state) if self.require_clean else None
        if error:
            return PreparedWorkspace(file_tree="", state=state.to_dict(), error=error)
        return PreparedWorkspace(
            file_tree=list_files(self.workspace),
            state=state.to_dict(),
        )

    def patch_path(self, iteration: int) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.patch_output_dir / f"patch_{timestamp}_attempt_{iteration}.patch"
