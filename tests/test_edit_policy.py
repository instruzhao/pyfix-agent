from pyfixagent.tools.edit_policy import EditPolicy, changed_lines_from_patch, paths_from_patch


def test_policy_enforces_allowed_and_forbidden_paths():
    policy = EditPolicy(allowed_paths=("src",))

    assert policy.validate_paths(["src/app.py"]) is None
    assert "outside allowed paths" in (policy.validate_paths(["package/app.py"]) or "")
    assert "forbidden path" in (policy.validate_paths(["src/tests/test_app.py"]) or "")
    assert ".py file" in (policy.validate_paths(["src/readme.md"]) or "")


def test_patch_metrics_extract_paths_and_changed_lines():
    patch = (
        "diff --git a/src/app.py b/src/app.py\n"
        "--- a/src/app.py\n"
        "+++ b/src/app.py\n"
        "@@ -1 +1 @@\n"
        "-old\n"
        "+new\n"
    )

    assert paths_from_patch(patch) == ["src/app.py"]
    assert changed_lines_from_patch(patch) == 2


def test_policy_enforces_file_and_line_budgets():
    policy = EditPolicy(max_files=1, max_changed_lines=2)

    assert "maximum is 1" in (policy.validate_paths(["a.py", "b.py"]) or "")
    assert policy.validate_changed_lines(2) is None
    assert "maximum is 2" in (policy.validate_changed_lines(3) or "")
