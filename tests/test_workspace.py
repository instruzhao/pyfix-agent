import subprocess

from pyfixagent.workspace import clean_workspace_error, inspect_workspace


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_workspace_inspection_distinguishes_clean_and_dirty(tmp_path):
    workspace = tmp_path / "repo"
    workspace.mkdir()
    _git(workspace, "init")
    _git(workspace, "config", "user.email", "tests@example.com")
    _git(workspace, "config", "user.name", "Tests")
    source = workspace / "app.py"
    source.write_text("value = 1\n", encoding="utf-8")
    _git(workspace, "add", ".")
    _git(workspace, "commit", "-m", "baseline")

    clean = inspect_workspace(workspace)
    assert clean.revision
    assert clean.dirty is False
    assert clean_workspace_error(clean) is None

    source.write_text("value = 2\n", encoding="utf-8")
    dirty = inspect_workspace(workspace)
    assert dirty.dirty is True
    assert "app.py" in dirty.changed_paths
    assert "uncommitted changes" in (clean_workspace_error(dirty) or "")
