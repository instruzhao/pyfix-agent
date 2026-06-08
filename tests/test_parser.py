from patch_eval.parser import parse_agent_output
from patch_eval.types import MARKDOWN_FENCE_FOUND


def test_parse_valid_json_patch_restores_newlines():
    raw = (
        '{"patch": "diff --git a/a.py b/a.py\\n--- a/a.py\\n+++ b/a.py\\n'
        '@@ -1,1 +1,1 @@\\n-old\\n+new\\n"}'
    )

    result = parse_agent_output(raw)

    assert result.cleaned_patch is not None
    assert "diff --git a/a.py b/a.py\n--- a/a.py" in result.cleaned_patch
    assert "\\n" not in result.cleaned_patch


def test_parse_json_patch_with_escaped_quotes():
    raw = (
        '{"patch": "diff --git a/a.py b/a.py\\n--- a/a.py\\n+++ b/a.py\\n'
        '@@ -1,1 +1,1 @@\\n-target_names = [\\"iris\\"]\\n+target_names = list(iris.target_names)\\n"}'
    )

    result = parse_agent_output(raw)

    assert result.cleaned_patch is not None
    assert 'target_names = ["iris"]' in result.cleaned_patch


def test_parse_markdown_fenced_diff():
    raw = """```diff
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-old
+new
```"""

    result = parse_agent_output(raw)

    assert result.cleaned_patch is not None
    assert result.cleaned_patch.startswith("--- a/a.py")
    assert MARKDOWN_FENCE_FOUND in result.warnings


def test_parse_markdown_fenced_json():
    raw = """```json
{"patch": "diff --git a/a.py b/a.py\\n--- a/a.py\\n+++ b/a.py\\n@@ -1,1 +1,1 @@\\n-old\\n+new\\n"}
```"""

    result = parse_agent_output(raw)

    assert result.cleaned_patch is not None
    assert result.source_type == "json:patch"


def test_parse_diff_with_explanation_text():
    raw = """Here is the patch:

diff --git a/a.py b/a.py
--- a/a.py
+++ b/a.py
@@ -1,1 +1,1 @@
-old
+new

Done."""

    result = parse_agent_output(raw)

    assert result.cleaned_patch is not None
    assert result.cleaned_patch.startswith("diff --git a/a.py b/a.py")
    assert "Here is" not in result.cleaned_patch
