import subprocess

from patch_eval.git_apply import run_git_apply_check
from patch_eval.types import CORRUPT_PATCH, GIT_APPLY_CHECK_FAILED, PATCH_CONTEXT_MISMATCH


def init_repo(tmp_path, content: str = "old\n"):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.py").write_text(content, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    return repo


def test_git_apply_check_passes_for_matching_patch(tmp_path):
    repo = init_repo(tmp_path)
    patch = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-old
+new
"""

    result = run_git_apply_check(repo, patch)

    assert result.ok
    assert result.error_type is None


def test_git_apply_check_classifies_context_mismatch(tmp_path):
    repo = init_repo(tmp_path, content="actual\n")
    patch = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-expected
+new
"""

    result = run_git_apply_check(repo, patch)

    assert not result.ok
    assert result.stderr
    assert result.error_type in {PATCH_CONTEXT_MISMATCH, GIT_APPLY_CHECK_FAILED}


def test_git_apply_check_classifies_bad_hunk_header(tmp_path):
    repo = init_repo(tmp_path, content="old\nanother context line\nbad\n")
    patch = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
 old
 another context line
-bad
+good
"""

    result = run_git_apply_check(repo, patch)

    assert not result.ok
    assert result.stderr
    assert result.error_type in {CORRUPT_PATCH, GIT_APPLY_CHECK_FAILED}
