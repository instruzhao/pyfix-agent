from pathlib import Path
import subprocess

from pyfixagent.execution.workspace_transaction import WorkspaceTransaction
from pyfixagent.workspace import inspect_workspace


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    repository = tmp_path / "repository"
    workspace = repository / "project"
    workspace.mkdir(parents=True)
    (workspace / "app.py").write_text("value = 1\n", encoding="utf-8")
    _git(repository, "init")
    _git(repository, "config", "user.email", "tests@example.com")
    _git(repository, "config", "user.name", "Tests")
    _git(repository, "add", ".")
    _git(repository, "commit", "-m", "baseline")
    return repository, workspace


def test_temporary_worktree_exports_patch_without_modifying_original(tmp_path):
    repository, workspace = _repository(tmp_path)
    transaction = WorkspaceTransaction(workspace, isolate=True)

    active = transaction.begin(inspect_workspace(workspace))
    assert active.workspace != workspace
    assert active.workspace.name == "project"
    (active.workspace / "app.py").write_text("value = 2\n", encoding="utf-8")
    transaction.checkpoint(1)
    patch = transaction.final_diff()

    assert "-value = 1" in patch
    assert "+value = 2" in patch
    assert (workspace / "app.py").read_text(encoding="utf-8") == "value = 1\n"
    worktree_root = active.git_root
    transaction.close()

    assert not worktree_root.exists()
    completed = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    )
    assert str(worktree_root) not in completed.stdout


def test_checkpoint_rollback_preserves_last_accepted_state(tmp_path):
    _, workspace = _repository(tmp_path)
    transaction = WorkspaceTransaction(workspace, isolate=True)
    active = transaction.begin(inspect_workspace(workspace))

    source = active.workspace / "app.py"
    source.write_text("value = 2\n", encoding="utf-8")
    transaction.checkpoint(1)
    source.write_text("value = 999\n", encoding="utf-8")
    (active.workspace / "temporary.py").write_text("bad = True\n", encoding="utf-8")
    transaction.rollback()

    assert source.read_text(encoding="utf-8") == "value = 2\n"
    assert not (active.workspace / "temporary.py").exists()
    transaction.close()
