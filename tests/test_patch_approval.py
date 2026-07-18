from pathlib import Path
import subprocess

import pytest

from pyfixagent.apply import apply_approved_patch, inspect_exported_patch, main


def _repository(tmp_path: Path) -> tuple[Path, Path]:
    repo = tmp_path / "repo"
    source = repo / "src" / "app.py"
    source.parent.mkdir(parents=True)
    source.write_text("VALUE = 1\n", encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", "commit", "-m", "base"],
        cwd=repo,
        check=True,
        capture_output=True,
    )
    source.write_text("VALUE = 2\n", encoding="utf-8")
    patch = tmp_path / "change.patch"
    patch.write_bytes(subprocess.run(["git", "diff", "--binary"], cwd=repo, check=True, capture_output=True).stdout)
    subprocess.run(["git", "restore", "--", "src/app.py"], cwd=repo, check=True)
    return repo, patch


def test_preview_binds_approval_to_cleaned_patch_without_mutating_workspace(tmp_path):
    repo, patch = _repository(tmp_path)

    approval = inspect_exported_patch(repo, patch, allowed_paths=("src",))

    assert len(approval.digest) == 64
    assert approval.modified_files == ("src/app.py",)
    assert approval.changed_lines == 2
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_wrong_approval_digest_never_applies_patch(tmp_path):
    repo, patch = _repository(tmp_path)
    approval = inspect_exported_patch(repo, patch, allowed_paths=("src",))

    with pytest.raises(ValueError, match="digest"):
        apply_approved_patch(approval, "0" * 64, allowed_paths=("src",))

    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_matching_approval_digest_applies_patch_and_leaves_it_uncommitted(tmp_path):
    repo, patch = _repository(tmp_path)
    approval = inspect_exported_patch(repo, patch, allowed_paths=("src",))

    apply_approved_patch(approval, approval.digest, allowed_paths=("src",))

    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 2\n"
    assert subprocess.run(["git", "status", "--porcelain"], cwd=repo, check=True, capture_output=True, text=True).stdout


def test_cli_preview_requires_approval_and_does_not_mutate(tmp_path, capsys):
    repo, patch = _repository(tmp_path)

    exit_code = main(["--workspace", str(repo), "--patch", str(patch), "--allowed-path", "src"])

    output = capsys.readouterr().out
    assert exit_code == 2
    assert "Approval required" in output
    assert "SHA-256:" in output
    assert (repo / "src" / "app.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_preview_rejects_dirty_workspace(tmp_path):
    repo, patch = _repository(tmp_path)
    (repo / "untracked.txt").write_text("dirty", encoding="utf-8")

    with pytest.raises(ValueError, match="uncommitted"):
        inspect_exported_patch(repo, patch, allowed_paths=("src",))
