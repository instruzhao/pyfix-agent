from patch_eval.normalizer import normalize_git_diff_headers
from patch_eval.types import MISSING_DIFF_GIT_HEADER_NORMALIZED


def test_normalize_traditional_unified_diff_adds_diff_git():
    patch = """--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-old
+new
"""

    result = normalize_git_diff_headers(patch)

    assert result.normalized_patch is not None
    assert result.normalized_patch.startswith("diff --git a/a.py b/a.py\n--- a/a.py")
    assert MISSING_DIFF_GIT_HEADER_NORMALIZED in result.warnings


def test_normalize_does_not_duplicate_existing_diff_git():
    patch = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-old
+new
"""

    result = normalize_git_diff_headers(patch)

    assert result.normalized_patch is not None
    assert result.normalized_patch.count("diff --git a/a.py b/a.py") == 1
