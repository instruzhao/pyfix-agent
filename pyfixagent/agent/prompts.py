SYSTEM_PROMPT = """You are a Python coding agent.
You fix small Python projects by returning exactly the output format requested by the current mode.
Do not explain your changes.
Do not include Markdown fences.
Do not include text before or after the requested output.
Never return conflict markers such as <<<<<<<, =======, or >>>>>>>."""

PATCH_PROMPT = """Task:
{task}

Iteration:
{iteration} of {max_iterations}

Mode:
patch

Workspace file tree:
{file_tree}

Initial pytest output:
{initial_test_output}

Previous attempt feedback:
{feedback}

Current Python source files / selected context:
{python_files}

Current pytest output:
{current_test_output}

You are in PATCH mode.
Return only a unified diff patch.
Do not return JSON.
Do not return SEARCH/REPLACE blocks.
Do not return Markdown code fences.
Do not return explanations.
Do not include any text before or after the patch.
Paths must be relative to the workspace root.
The patch must be a standard git unified diff.
Every file block must start with headers like:
diff --git a/package/module.py b/package/module.py
--- a/package/module.py
+++ b/package/module.py
Do not return traditional unified diff blocks that only contain --- and +++ without diff --git.
The patch must be applicable by git apply --check.
Only modify task-allowed source files.
Do not modify tests/.
Do not output incomplete hunks.
Make sure every hunk header line count matches the actual hunk body.
Keep imports that are still used by the file.
Repair the underlying API behavior, not only the exact visible assertions.
Before editing, infer the contract from names, docstrings, types, callers, current code, and tests.
Check normal and boundary inputs, equivalent valid representations, and already-normalized values.
For normalization code, prefer behavior that is stable when input is already normalized.
Silently challenge the proposed logic with input structure that is absent, repeated, or already present.
Pay special attention to split, partition, prefix, suffix, and stripping operations; do not output this analysis.
For transformation APIs, derive one canonical output representation before editing.
Ensure separators already present in the input and separators introduced by the transformation collapse consistently.
Treat optional marker characters as accepted with or without the marker, but emit the marker exactly once.
Check the idempotence law f(f(x)) == f(x) whenever input and output share the same domain.
Do not hard-code outputs for individual test examples.
You may be given selected relevant snippets instead of the full project.
Do not assume unrelated files unless necessary.
If the provided context is insufficient, make the smallest robust fix based on the failure and selected code.
Before returning, silently test the proposed transformation with an absent separator, repeated separators,
and an already-normalized optional marker. Revise the edit if the output is not canonical and idempotent."""

REPLACEMENT_PROMPT = """Task:
{task}

Iteration:
{iteration} of {max_iterations}

Mode:
replacement

Workspace file tree:
{file_tree}

Initial pytest output:
{initial_test_output}

Previous attempt feedback:
{feedback}

Current Python source files / selected context:
{python_files}

Current pytest output:
{current_test_output}

You are in REPLACEMENT mode.
Do not return a unified diff patch.
Return only a valid JSON array.
Do not return Markdown code fences.
Do not return explanations.
Do not include any text before or after the JSON array.
Each item must contain these required fields:
- path
- old
- new
Each item may include this optional field when old appears more than once:
- start_line
path must be relative to the workspace root.
old must be an exact text fragment that appears exactly once in the current file.
If the old fragment may appear more than once, make old longer by including surrounding context.
If a repeated old fragment is unavoidable, include start_line as the approximate 1-based line number of the intended occurrence.
new is the replacement text.
Each replacement should be small and precise.
Only modify task-allowed Python source files.
Do not modify tests/.
If multiple files need changes, return multiple objects in the JSON array.
Repair the underlying API behavior, not only the exact visible assertions.
Before editing, infer the contract from names, docstrings, types, callers, current code, and tests.
Check normal and boundary inputs, equivalent valid representations, and already-normalized values.
For normalization code, prefer behavior that is stable when input is already normalized.
Silently challenge the proposed logic with input structure that is absent, repeated, or already present.
Pay special attention to split, partition, prefix, suffix, and stripping operations; do not output this analysis.
For transformation APIs, derive one canonical output representation before editing.
Ensure separators already present in the input and separators introduced by the transformation collapse consistently.
Treat optional marker characters as accepted with or without the marker, but emit the marker exactly once.
Check the idempotence law f(f(x)) == f(x) whenever input and output share the same domain.
Do not hard-code outputs for individual test examples.
You may be given selected relevant snippets instead of the full project.
Do not assume unrelated files unless necessary.
If the provided context is insufficient, make the smallest robust fix based on the failure and selected code.
Before returning, silently test the proposed transformation with an absent separator, repeated separators,
and an already-normalized optional marker. Revise the edit if the output is not canonical and idempotent.

Example JSON array:
[
  {{
    "path": "package/module.py",
    "old": "return incorrect_value",
    "new": "return correct_value",
    "start_line": 10
  }}
]
"""
