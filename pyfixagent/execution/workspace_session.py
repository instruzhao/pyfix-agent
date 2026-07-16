from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pyfixagent.execution.workspace_transaction import WorkspaceTransaction
from pyfixagent.tools.file_tools import list_files
from pyfixagent.workspace import clean_workspace_error, inspect_workspace


@dataclass(frozen=True)
class PreparedWorkspace:
    workspace: Path
    file_tree: str
    state: dict
    strategy: str
    error: str | None = None


class WorkspaceSession:
    """Owns run setup and generated artifact paths for one workspace."""

    def __init__(
        self,
        workspace: Path,
        patch_output_dir: Path,
        require_clean: bool = False,
        isolate: bool = False,
    ):
        self.workspace = Path(workspace)
        self.patch_output_dir = Path(patch_output_dir)
        self.require_clean = require_clean
        self.transaction = WorkspaceTransaction(self.workspace, isolate=isolate)

    def prepare(self) -> PreparedWorkspace:
        state = inspect_workspace(self.workspace)
        error = clean_workspace_error(state) if self.require_clean else None
        strategy = (
            "temporary_git_worktree"
            if self.transaction.isolate
            else "in_place_clean_guard"
            if self.require_clean
            else "incremental_repair"
        )
        if error:
            return PreparedWorkspace(
                workspace=self.workspace,
                file_tree="",
                state=state.to_dict(),
                strategy=strategy,
                error=error,
            )
        try:
            active = self.transaction.begin(state)
        except Exception as exc:
            return PreparedWorkspace(
                workspace=self.workspace,
                file_tree="",
                state=state.to_dict(),
                strategy=strategy,
                error=str(exc),
            )
        state_data = state.to_dict()
        state_data["active_workspace"] = str(active.workspace)
        state_data["isolated"] = active.isolated
        return PreparedWorkspace(
            workspace=active.workspace,
            file_tree=list_files(active.workspace),
            state=state_data,
            strategy=strategy,
        )

    def patch_path(self, iteration: int) -> Path:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return self.patch_output_dir / f"patch_{timestamp}_attempt_{iteration}.patch"

    def checkpoint(self, iteration: int) -> None:
        self.transaction.checkpoint(iteration)

    def rollback(self) -> None:
        self.transaction.rollback()

    def export_final_patch(self) -> tuple[str, Path | None]:
        patch = self.transaction.final_diff()
        if not patch:
            return "", None
        self.patch_output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = self.patch_output_dir / f"final_{timestamp}.patch"
        path.write_text(patch, encoding="utf-8", newline="\n")
        return patch, path

    def close(self) -> None:
        self.transaction.close()
