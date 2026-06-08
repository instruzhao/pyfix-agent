PATCH_OUTPUT_PROMPT = """You are the agent being evaluated.

Your final output must be exactly one valid JSON object:

{
  "patch": "<standard git unified diff string>"
}

Strict output rules:
1. Output must be directly parseable by json.loads().
2. Do not output Markdown.
3. Do not output json, diff, or patch code fences.
4. Do not output explanations.
5. Do not output any text outside the JSON object.
6. The patch field must be a string.
7. Newlines inside the patch string must be written as \\n.
8. Double quotes inside the patch string must be escaped as \\".
9. The JSON object must not contain a trailing comma.
10. The patch must be a standard git unified diff.
11. Every file block must contain:
diff --git a/<path> b/<path>
--- a/<path>
+++ b/<path>
12. Every hunk must contain a legal hunk header:
@@ -old_start,old_count +new_start,new_count @@
13. Each hunk header old_count/new_count must match the hunk body.
14. The patch should pass git apply --check.
15. Do not output traditional unified diff blocks that only have --- and +++ without diff --git.
16. Do not output Markdown fences such as ```json or ```diff."""
