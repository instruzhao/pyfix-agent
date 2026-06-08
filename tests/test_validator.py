from patch_eval.types import MISSING_HUNK_HEADER, SPECIAL_WHITESPACE_FOUND, UNSAFE_PATH
from patch_eval.validator import validate_patch_format


def test_validate_rejects_missing_hunk_header():
    patch = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
-old
+new
"""

    result = validate_patch_format(patch)

    assert not result.ok
    assert MISSING_HUNK_HEADER in result.errors


def test_validate_rejects_unsafe_path():
    patch = """diff --git a/../secret.py b/../secret.py
--- a/../secret.py
+++ b/../secret.py
@@ -1,1 +1,1 @@
-old
+new
"""

    result = validate_patch_format(patch)

    assert not result.ok
    assert UNSAFE_PATH in result.errors


def test_validate_rejects_special_whitespace():
    patch = "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n@@ -1,1 +1,1 @@\n-old\n+new\xa0\n"

    result = validate_patch_format(patch)

    assert not result.ok
    assert SPECIAL_WHITESPACE_FOUND in result.errors
