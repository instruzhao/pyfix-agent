from dataclasses import asdict, dataclass
from pathlib import Path
import subprocess


@dataclass(frozen=True)
class WorkspaceState:
    git_root: str | None
    revision: str | None
    dirty: bool
    changed_paths: tuple[str, ...]
    error: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def inspect_workspace(workspace: str | Path) -> WorkspaceState:
    path = Path(workspace).resolve()
    if not path.exists():
        return WorkspaceState(None, None, False, (), f"workspace does not exist: {path}")

    root_result = _git(path, ["rev-parse", "--show-toplevel"])
    if root_result.returncode != 0:
        return WorkspaceState(None, None, False, (), "workspace is not inside a Git working tree")

    git_root = root_result.stdout.strip()
    revision_result = _git(path, ["rev-parse", "HEAD"])
    revision = revision_result.stdout.strip() if revision_result.returncode == 0 else None
    status_result = _git(path, ["status", "--porcelain", "--untracked-files=all", "--", "."])
    if status_result.returncode != 0:
        return WorkspaceState(git_root, revision, False, (), status_result.stderr.strip() or "git status failed")

    changed_paths = tuple(
        line[3:].strip().replace("\\", "/")
        for line in status_result.stdout.splitlines()
        if len(line) >= 4
    )
    return WorkspaceState(git_root, revision, bool(changed_paths), changed_paths)


def clean_workspace_error(state: WorkspaceState) -> str | None:
    if state.error:
        return state.error
    if state.revision is None:
        return "workspace Git repository has no HEAD commit"
    if state.dirty:
        preview = ", ".join(state.changed_paths[:5])
        suffix = "..." if len(state.changed_paths) > 5 else ""
        return f"workspace has uncommitted changes: {preview}{suffix}"
    return None


def _git(cwd: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        timeout=15,
        capture_output=True,
        text=True,
        check=False,
    )
