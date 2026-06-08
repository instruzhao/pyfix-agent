import subprocess

from pyfixagent.tools.patch_tools import (
    apply_patch,
    check_patch,
    clean_model_output,
    clean_patch_text,
    normalize_git_diff_headers,
    save_patch,
    validate_patch_format,
)


def test_apply_valid_patch(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    file_path = tmp_path / "hello.py"
    file_path.write_text("def message():\n    return 'old'\n", encoding="utf-8")
    subprocess.run(["git", "add", "hello.py"], cwd=tmp_path, check=True, capture_output=True)

    patch = """diff --git a/hello.py b/hello.py
index 85d7b2a..0000000 100644
--- a/hello.py
+++ b/hello.py
@@ -1,2 +1,2 @@
 def message():
-    return 'old'
+    return 'new'
"""

    result = apply_patch(tmp_path, patch)

    assert result.success
    assert "new" in file_path.read_text(encoding="utf-8")


def test_apply_invalid_patch_returns_failure(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)

    result = apply_patch(tmp_path, "not a patch")

    assert not result.success
    assert result.error


def test_check_invalid_patch_does_not_modify_workspace(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    file_path = tmp_path / "hello.py"
    file_path.write_text("VALUE = 'old'\n", encoding="utf-8")

    result = check_patch(tmp_path, "not a patch")

    assert not result.success
    assert result.error
    assert file_path.read_text(encoding="utf-8") == "VALUE = 'old'\n"


def test_save_patch_cleans_markdown_fence(tmp_path):
    output = tmp_path / "patches" / "fix.patch"

    saved = save_patch(tmp_path, "```diff\n--- a/a.py\n+++ b/a.py\n@@ -1,1 +1,1 @@\n-old\n+new\n```", output)

    assert saved == output
    assert saved.read_text(encoding="utf-8") == (
        "diff --git a/a.py b/a.py\n"
        "--- a/a.py\n"
        "+++ b/a.py\n"
        "@@ -1,1 +1,1 @@\n"
        "-old\n"
        "+new\n"
    )


def test_clean_patch_text_does_not_rewrite_hunk_header_counts():
    patch = """Here is the patch:
```diff
--- a/hello.py
+++ b/hello.py
@@ -11,9 +11,9 @@ def message():
 line 1
-old
+new
```
"""

    cleaned = clean_patch_text(patch)

    assert cleaned.startswith("diff --git a/hello.py b/hello.py")
    assert "@@ -11,9 +11,9 @@ def message():" in cleaned
    assert "@@ -11,10 +11,10 @@" not in cleaned


def test_clean_patch_text_keeps_content_from_first_unified_diff_marker():
    patch = """I fixed the issue below.

Some explanation that should be removed.
diff --git a/hello.py b/hello.py
--- a/hello.py
+++ b/hello.py
@@ -1,2 +1,2 @@
-old
+new
"""

    cleaned = clean_patch_text(patch)

    assert cleaned.startswith("diff --git a/hello.py b/hello.py")
    assert "Some explanation" not in cleaned


def test_clean_patch_does_not_modify_hunk_header():
    patch = """--- a/hello.py
+++ b/hello.py
@@ -10,9 +10,9 @@ def message():
 line 1
-old
+new
"""

    cleaned = clean_patch_text(patch)

    assert "@@ -10,9 +10,9 @@ def message():" in cleaned


def test_clean_patch_removes_markdown_fence_only():
    patch = """```diff
--- a/hello.py
+++ b/hello.py
@@ -10,9 +10,9 @@ def message():
 line 1
-old
+new
```"""

    cleaned = clean_patch_text(patch)

    assert cleaned == """diff --git a/hello.py b/hello.py
--- a/hello.py
+++ b/hello.py
@@ -10,9 +10,9 @@ def message():
 line 1
-old
+new
"""


def test_clean_patch_extracts_patch_from_explanation_without_rewriting_hunks():
    patch = """Here is the patch. It fixes the bug.

--- a/hello.py
+++ b/hello.py
@@ -10,9 +10,9 @@ def message():
 line 1
-old
+new

Thanks.
"""

    cleaned = clean_patch_text(patch)

    assert cleaned.startswith("diff --git a/hello.py b/hello.py")
    assert "Here is the patch" not in cleaned
    assert "@@ -10,9 +10,9 @@ def message():" in cleaned


def test_clean_model_output_extracts_patch_from_valid_json_object():
    raw = (
        '{"patch": "diff --git a/a.py b/a.py\\n--- a/a.py\\n+++ b/a.py\\n'
        '@@ -1,1 +1,1 @@\\n-old\\n+new\\n"}'
    )

    cleaned = clean_patch_text(raw)

    assert cleaned.startswith("diff --git a/a.py b/a.py")
    assert validate_patch_format(cleaned).success


def test_normalize_git_diff_headers_adds_missing_diff_git():
    patch = """--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-old
+new
"""

    normalized = normalize_git_diff_headers(patch)

    assert normalized.startswith("diff --git a/a.py b/a.py\n--- a/a.py")


def test_markdown_fenced_traditional_diff_cleans_and_validates():
    raw = """```diff
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-old
+new
```"""

    cleaned = clean_patch_text(raw)

    assert "```" not in cleaned
    assert cleaned.startswith("diff --git a/a.py b/a.py")
    assert validate_patch_format(cleaned).success


def test_json_patch_with_quotes_restores_real_quotes():
    raw = (
        '{"patch": "diff --git a/a.py b/a.py\\n--- a/a.py\\n+++ b/a.py\\n'
        '@@ -1,1 +1,1 @@\\n-target_names = [\\"iris\\"]\\n'
        '+target_names = list(iris.target_names)\\n"}'
    )

    cleaned = clean_model_output(raw)

    assert 'target_names = ["iris"]' in cleaned


def test_validate_patch_format_rejects_missing_hunk_header():
    patch = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
-old
+new
"""

    result = validate_patch_format(patch)

    assert not result.success
    assert result.error_code == "MISSING_HUNK_HEADER"


def test_validate_patch_format_rejects_unsafe_path():
    patch = """diff --git a/../a.py b/../a.py
--- a/../a.py
+++ b/../a.py
@@ -1,1 +1,1 @@
-old
+new
"""

    result = validate_patch_format(patch)

    assert not result.success
    assert result.error_code == "UNSAFE_PATH"


def test_check_patch_returns_git_apply_check_failed_for_context_mismatch(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    file_path = tmp_path / "a.py"
    file_path.write_text("actual\n", encoding="utf-8")
    subprocess.run(["git", "add", "a.py"], cwd=tmp_path, check=True, capture_output=True)
    patch = """diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-expected
+new
"""

    result = check_patch(tmp_path, patch)

    assert not result.success
    assert result.error and result.error.startswith("GIT_APPLY_CHECK_FAILED")
