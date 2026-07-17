from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile

from pyfixagent.workspace import WorkspaceState


@dataclass(frozen=True)
class ActiveWorkspace:
    original_workspace: Path
    workspace: Path
    git_root: Path
    revision: str
    isolated: bool


class WorkspaceTransaction:
    """Owns temporary worktree creation, checkpoints, rollback, and cleanup."""

    def __init__(self, workspace: Path, *, isolate: bool = False):
        self.original_workspace = Path(workspace).resolve()
        self.isolate = isolate
        self.active: ActiveWorkspace | None = None
        self._temporary_root: Path | None = None

    def begin(self, state: WorkspaceState) -> ActiveWorkspace:
        if self.active is not None:
            raise RuntimeError("workspace transaction has already started")
        if state.git_root is None:
            raise RuntimeError(state.error or "workspace is not inside a Git working tree")

        git_root = Path(state.git_root).resolve()
        if not self.isolate:
            self.active = ActiveWorkspace(
                original_workspace=self.original_workspace,
                workspace=self.original_workspace,
                git_root=git_root,
                revision=state.revision or "",
                isolated=False,
            )
            return self.active

        if state.revision is None:
            raise RuntimeError("workspace Git repository has no HEAD commit")

        try:
            relative_workspace = self.original_workspace.relative_to(git_root)
        except ValueError as exc:
            raise RuntimeError("workspace is outside its reported Git root") from exc

        temporary_root = Path(tempfile.mkdtemp(prefix="pyfixagent-worktree-")).resolve()
        worktree_root = temporary_root / "repo"
        completed = self._git(
            git_root,
            ["worktree", "add", "--detach", str(worktree_root), state.revision],
            timeout=60,
        )
        if completed.returncode != 0:
            self._safe_remove(temporary_root)
            message = completed.stderr.strip() or completed.stdout.strip() or "git worktree add failed"
            raise RuntimeError(message)

        active_workspace = (worktree_root / relative_workspace).resolve()
        if not active_workspace.is_dir():
            self._remove_worktree(git_root, worktree_root)
            self._safe_remove(temporary_root)
            raise RuntimeError(f"workspace path is missing from temporary worktree: {relative_workspace}")

        self._temporary_root = temporary_root
        self.active = ActiveWorkspace(
            original_workspace=self.original_workspace,
            workspace=active_workspace,
            git_root=worktree_root,
            revision=state.revision,
            isolated=True,
        )
        return self.active

    def checkpoint(self, iteration: int, kind: str = "iteration") -> str | None:
        active = self._require_active()
        if not active.isolated:
            return None
        add = self._git(active.workspace, ["add", "-A", "--", "."])
        if add.returncode != 0:
            raise RuntimeError(add.stderr.strip() or "failed to stage worktree checkpoint")
        staged = self._git(active.workspace, ["diff", "--cached", "--quiet", "--", "."])
        if staged.returncode == 0:
            return self._head(active.workspace)
        if staged.returncode != 1:
            raise RuntimeError(staged.stderr.strip() or "failed to inspect worktree checkpoint")
        commit = self._git(
            active.workspace,
            [
                "-c",
                "user.name=PyFixAgent",
                "-c",
                "user.email=pyfixagent@local.invalid",
                "commit",
                "--no-verify",
                "--no-gpg-sign",
                "-m",
                f"pyfixagent: checkpoint {kind} {iteration}",
            ],
        )
        if commit.returncode != 0:
            raise RuntimeError(commit.stderr.strip() or "failed to create worktree checkpoint")
        return self._head(active.workspace)

    def rollback(self) -> None:
        active = self._require_active()
        if not active.isolated:
            return
        reset = self._git(active.workspace, ["reset", "--hard", "HEAD"])
        if reset.returncode != 0:
            raise RuntimeError(reset.stderr.strip() or "failed to roll back worktree")
        clean = self._git(active.workspace, ["clean", "-fd", "--", "."])
        if clean.returncode != 0:
            raise RuntimeError(clean.stderr.strip() or "failed to clean rolled-back worktree")

    def final_diff(self) -> str:
        active = self._require_active()
        if active.isolated:
            completed = self._git(
                active.git_root,
                ["diff", "--binary", active.revision, "HEAD", "--", "."],
            )
        else:
            completed = self._git(active.workspace, ["diff", "--binary", "--", "."])
        if completed.returncode != 0:
            raise RuntimeError(completed.stderr.strip() or "failed to export final patch")
        return completed.stdout

    @classmethod
    def _head(cls, workspace: Path) -> str | None:
        completed = cls._git(workspace, ["rev-parse", "HEAD"])
        return completed.stdout.strip() if completed.returncode == 0 else None

    def close(self) -> None:
        active = self.active
        temporary_root = self._temporary_root
        self.active = None
        self._temporary_root = None
        if active is None or not active.isolated:
            return
        error = self._remove_worktree(Path(active.original_workspace).resolve(), active.git_root)
        if temporary_root is not None:
            self._safe_remove(temporary_root)
        if error:
            raise RuntimeError(error)

    def _require_active(self) -> ActiveWorkspace:
        if self.active is None:
            raise RuntimeError("workspace transaction has not started")
        return self.active

    @classmethod
    def _remove_worktree(cls, cwd: Path, worktree_root: Path) -> str | None:
        root = cls._git(cwd, ["rev-parse", "--show-toplevel"])
        git_root = Path(root.stdout.strip()) if root.returncode == 0 else cwd
        completed = cls._git(
            git_root,
            ["worktree", "remove", "--force", str(worktree_root)],
            timeout=60,
        )
        cls._git(git_root, ["worktree", "prune"])
        if completed.returncode != 0 and worktree_root.exists():
            return completed.stderr.strip() or "failed to remove temporary worktree"
        return None

    @staticmethod
    def _git(cwd: Path, args: list[str], timeout: int = 30) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
        )

    @staticmethod
    def _safe_remove(path: Path) -> None:
        resolved = path.resolve()
        temporary_root = Path(tempfile.gettempdir()).resolve()
        try:
            resolved.relative_to(temporary_root)
        except ValueError as exc:
            raise RuntimeError(f"refusing to remove path outside temporary directory: {resolved}") from exc
        if resolved.exists():
            shutil.rmtree(resolved, onerror=WorkspaceTransaction._remove_readonly)

    @staticmethod
    def _remove_readonly(function, path, _exc_info) -> None:
        os.chmod(path, stat.S_IWRITE)
        function(path)
