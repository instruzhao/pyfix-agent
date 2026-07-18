import json
from pathlib import Path
import subprocess

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.main import save_trace
from pyfixagent.models.mock_model import MockModel
from pyfixagent.sandbox.base import CommandResult
from pyfixagent.sandbox.local_sandbox import LocalSandbox


def init_workspace(tmp_path, source: str, test_source: str):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "calculator.py").write_text(source, encoding="utf-8")
    (workspace / "test_calculator.py").write_text(test_source, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    return workspace


def make_agent(workspace, tmp_path, model, max_iterations=3, initial_mode="patch"):
    return DefaultAgent(
        model=model,
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        max_iterations=max_iterations,
        initial_mode=initial_mode,
    )


def pytest_test_for_divide():
    return (
        "import pytest\n"
        "from calculator import divide\n\n"
        "def test_divide_regular_case():\n"
        "    assert divide(6, 2) == 3\n\n"
        "def test_divide_by_zero_raises_value_error():\n"
        "    with pytest.raises(ValueError):\n"
        "        divide(1, 0)\n"
    )


def divide_zero_patch():
    return """--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,4 @@
 def divide(a, b):
+    if b == 0:
+        raise ValueError("division by zero")
     return a / b
"""


def test_initial_execution_infrastructure_error_stops_before_model_call(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def divide(a, b):\n    return a / b\n",
        pytest_test_for_divide(),
    )
    model = MockModel([])

    class BrokenSandbox(LocalSandbox):
        def run(self, command, timeout=None):
            return CommandResult(
                command=list(command),
                exit_code=125,
                stdout="",
                stderr="container daemon unavailable",
                duration=0.01,
                backend="container",
                infrastructure_error=True,
            )

    agent = DefaultAgent(
        model=model,
        sandbox=BrokenSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        max_iterations=1,
        initial_mode="patch",
    )

    result = agent.run("Fix tests.")

    assert result.success is False
    assert "infrastructure error" in result.error
    assert model.calls == 0
    assert result.iterations == []


def test_first_patch_success_and_pytest_passes(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def divide(a, b):\n    return a / b\n",
        pytest_test_for_divide(),
    )
    model = MockModel([divide_zero_patch()])

    result = make_agent(workspace, tmp_path, model, max_iterations=1).run("Fix tests.")

    assert result.success
    assert result.final_patch_command == "git diff --"
    assert model.calls == 1
    assert len(result.iterations) == 1
    record = result.iterations[0]
    assert record.raw_model_output == divide_zero_patch()
    assert "Selected context strategy:" in record.prompt
    assert record.context is not None
    assert record.context["strategy"] == "traceback"
    assert record.context["dependency_analysis"] is False
    assert record.context["stats"]["selected_file_count"] >= 1
    assert record.context["selected_files"]
    assert all(item["reason"] in {"failing_test_file", "traceback_source_file", "direct_test_import"} for item in record.context["selected_files"])
    assert record.test_summary_before is not None
    assert record.test_summary_after is not None
    assert record.failure_delta is not None
    assert record.iteration_result["failure_type"] == "success"
    assert record.generated_diff.startswith("diff --git")
    assert record.model_output["mode"] == "patch"
    assert record.apply["method"] == "patch"
    assert record.apply["success"] is True
    assert record.edit_summary["modified_files"] == ["calculator.py"]
    assert record.model_call["provider"] == "mock"
    assert "raise ValueError" in record.cleaned_patch
    assert record.cleaned_patch.startswith("diff --git a/calculator.py b/calculator.py")
    assert record.apply_check_success
    assert record.apply_success
    assert record.pytest_exit_code == 0


def test_patch_check_failure_then_second_patch_success(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def divide(a, b):\n    return a / b\n",
        pytest_test_for_divide(),
    )
    model = MockModel(["not a patch", divide_zero_patch()])

    result = make_agent(workspace, tmp_path, model, max_iterations=2).run("Fix tests.")

    assert result.success
    assert model.calls == 2
    assert len(result.iterations) == 2
    assert not result.iterations[0].apply_check_success
    assert not result.iterations[0].apply_success
    assert result.iterations[0].apply_check_error
    assert result.iterations[0].patch_command == "git apply --check -"
    assert "return a / b" in (workspace / "calculator.py").read_text(encoding="utf-8")
    assert result.iterations[1].apply_check_success
    assert result.iterations[1].success


def test_falls_back_to_replacement_after_two_patch_check_failures(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def divide(a, b):\n    return a / b\n",
        pytest_test_for_divide(),
    )
    replacement = (
        '[{"path": "calculator.py", '
        '"old": "def divide(a, b):\\n    return a / b\\n", '
        '"new": "def divide(a, b):\\n    if b == 0:\\n        raise ValueError(\\"division by zero\\")\\n    return a / b\\n"}]'
    )
    model = MockModel(["not a patch", "still not a patch", replacement])

    result = make_agent(workspace, tmp_path, model, max_iterations=3).run("Fix tests.")

    assert result.success
    assert result.final_patch_command == "git diff --"
    assert model.calls == 3
    assert [record.mode for record in result.iterations] == ["patch", "patch", "replacement"]
    assert not result.iterations[0].apply_check_success
    assert not result.iterations[1].apply_check_success
    assert result.iterations[2].replacement_raw_output == replacement
    assert result.iterations[2].cleaned_patch.startswith("diff --git a/calculator.py b/calculator.py")
    assert result.iterations[2].model_output_type == "replacement"
    assert result.iterations[2].patch_command == "git diff --"
    assert result.iterations[2].replacement_success is True
    assert result.iterations[2].replacement_edits == [
        {
            "path": "calculator.py",
            "old": "def divide(a, b):\n    return a / b\n",
            "new": (
                "def divide(a, b):\n"
                "    if b == 0:\n"
                "        raise ValueError(\"division by zero\")\n"
                "    return a / b\n"
            ),
        }
    ]
    assert result.iterations[2].pytest_exit_code == 0


def test_default_agent_starts_in_replacement_mode(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def divide(a, b):\n    return a / b\n",
        pytest_test_for_divide(),
    )
    replacement = (
        '[{"path": "calculator.py", '
        '"old": "def divide(a, b):\\n    return a / b\\n", '
        '"new": "def divide(a, b):\\n    if b == 0:\\n        raise ValueError(\\"division by zero\\")\\n    return a / b\\n"}]'
    )
    model = MockModel([replacement])

    result = DefaultAgent(
        model=model,
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        max_iterations=1,
    ).run("Fix tests.")

    assert result.success
    assert result.environment is not None
    assert result.final_summary is not None
    assert result.final_summary["status"] == "passed"
    assert [record.mode for record in result.iterations] == ["replacement"]
    assert result.iterations[0].model_output_type == "replacement"
    assert result.iterations[0].patch_command == "git diff --"


def test_replacement_failure_feedback_is_sent_to_next_iteration(tmp_path):
    test_source = (
        "from ambiguous import choose_second\n\n"
        "def test_choose_second():\n"
        "    assert choose_second() is True\n"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "ambiguous.py").write_text(
        "def choose_first():\n"
        "    return False\n\n\n"
        "def choose_second():\n"
        "    return False\n",
        encoding="utf-8",
    )
    (workspace / "test_ambiguous.py").write_text(test_source, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    first_replacement = '[{"path": "ambiguous.py", "old": "return False", "new": "return True"}]'
    second_replacement = (
        '[{"path": "ambiguous.py", "old": "return False", "new": "return True", "start_line": 6}]'
    )
    model = MockModel([first_replacement, second_replacement])

    result = DefaultAgent(
        model=model,
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        max_iterations=2,
    ).run("Fix tests.")

    assert result.success
    assert len(result.iterations) == 2
    assert result.iterations[0].replacement_success is False
    assert "appears multiple times" in (result.iterations[0].replacement_error or "")
    assert "appears multiple times" in model.prompts[1]
    assert "start_line" in model.prompts[1]
    assert result.iterations[1].replacement_success is True
    assert result.iterations[1].replacement_edits == [
        {
            "path": "ambiguous.py",
            "old": "return False",
            "new": "return True",
            "start_line": 6,
        }
    ]


def test_stays_in_replacement_mode_after_replacement_pytest_failure(tmp_path):
    test_source = (
        "import pytest\n"
        "from calc_multi import divide, increment\n\n"
        "def test_divide_regular_case():\n"
        "    assert divide(6, 2) == 3\n\n"
        "def test_divide_by_zero_raises_value_error():\n"
        "    with pytest.raises(ValueError):\n"
        "        divide(1, 0)\n\n"
        "def test_increment():\n"
        "    assert increment(2) == 3\n"
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "calc_multi.py").write_text(
        "def divide(a, b):\n    return a / b\n\n\ndef increment(value):\n    return value - 1\n",
        encoding="utf-8",
    )
    (workspace / "test_calc_multi.py").write_text(test_source, encoding="utf-8")
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    first_replacement = (
        '[{"path": "calc_multi.py", '
        '"old": "def divide(a, b):\\n    return a / b\\n", '
        '"new": "def divide(a, b):\\n    if b == 0:\\n        raise ValueError(\\"division by zero\\")\\n    return a / b\\n"}]'
    )
    second_replacement = (
        '[{"path": "calc_multi.py", '
        '"old": "def increment(value):\\n    return value - 1\\n", '
        '"new": "def increment(value):\\n    return value + 1\\n"}]'
    )
    model = MockModel(["not a patch", "still not a patch", first_replacement, second_replacement])

    result = make_agent(workspace, tmp_path, model, max_iterations=4).run("Fix tests.")

    assert result.success is True
    assert [record.mode for record in result.iterations] == [
        "patch",
        "patch",
        "replacement",
        "replacement",
    ]
    assert result.iterations[2].model_output_type == "replacement"
    assert result.iterations[3].model_output_type == "replacement"
    assert result.iterations[2].replacement_edits
    assert result.iterations[3].replacement_edits
    assert result.iterations[2].pytest_exit_code == 1
    assert result.iterations[3].pytest_exit_code == 0
    final_source = (workspace / "calc_multi.py").read_text(encoding="utf-8")
    assert 'raise ValueError("division by zero")' in final_source
    assert "return value + 1" in final_source

    trace_path = save_trace(result, tmp_path / "traces")
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    assert trace["iterations"][2]["model_output_type"] == "replacement"
    assert trace["iterations"][3]["model_output_type"] == "replacement"
    assert trace["iterations"][2]["context"]["strategy"] == "traceback"
    assert trace["iterations"][2]["context"]["prompt_chars"] > 0
    assert trace["iterations"][2]["model_output"]["parsed_edits"] == trace["iterations"][2]["replacement_edits"]
    assert trace["iterations"][2]["apply"]["method"] == "replacement"
    assert trace["iterations"][2]["generated_diff"] == trace["iterations"][2]["apply"]["generated_diff"]
    assert trace["environment"]["python"]
    assert trace["final_summary"]["status"] == "passed"


def test_patch_applies_but_pytest_fails_then_second_patch_success(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def divide(a, b):\n    return a / b\n",
        pytest_test_for_divide(),
    )
    first_patch = """--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,4 @@
 def divide(a, b):
+    if b == 0:
+        return 0
     return a / b
"""
    second_patch = """--- a/calculator.py
+++ b/calculator.py
@@ -1,4 +1,4 @@
 def divide(a, b):
     if b == 0:
-        return 0
+        raise ValueError("division by zero")
     return a / b
"""
    model = MockModel([first_patch, second_patch])

    result = make_agent(workspace, tmp_path, model, max_iterations=2).run("Fix tests.")

    assert result.success
    assert len(result.iterations) == 2
    assert result.iterations[0].apply_success
    assert result.iterations[0].pytest_exit_code == 1
    assert result.iterations[0].pytest_output
    assert "return 0" not in (workspace / "calculator.py").read_text(encoding="utf-8")
    assert result.iterations[1].pytest_exit_code == 0


def test_stops_after_max_iterations(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def divide(a, b):\n    return a / b\n",
        pytest_test_for_divide(),
    )
    model = MockModel(["not a patch", "still not a patch"])

    result = make_agent(workspace, tmp_path, model, max_iterations=2).run("Fix tests.")

    assert not result.success
    assert model.calls == 2
    assert len(result.iterations) == 2
    assert result.final_patch_command == "git apply --check -"
    assert result.iterations[0].patch_command == "git apply --check -"
    assert result.iterations[1].patch_command == "git apply --check -"
    assert "reached max_iterations=2" in (result.error or "")


def test_initial_pytest_passes_does_not_call_model(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def add(a, b):\n    return a + b\n",
        "from calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
    )
    model = MockModel([divide_zero_patch()])

    result = make_agent(workspace, tmp_path, model, max_iterations=3).run("Fix tests.")

    assert result.success
    assert model.calls == 0
    assert result.iterations == []


def test_isolated_agent_exports_patch_and_preserves_original_workspace(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def divide(a, b):\n    return a / b\n",
        pytest_test_for_divide(),
    )
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace, check=True, capture_output=True)
    original = (workspace / "calculator.py").read_text(encoding="utf-8")
    model = MockModel([divide_zero_patch()])
    agent = DefaultAgent(
        model=model,
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        max_iterations=1,
        initial_mode="patch",
        require_clean_workspace=True,
        isolate_workspace=True,
    )

    result = agent.run("Fix tests.")

    assert result.success is True
    assert result.workspace_strategy == "temporary_git_worktree"
    assert result.iterations[0].workspace_action == "checkpointed_success"
    assert result.final_patch_path
    assert Path(result.final_patch_path).exists()
    assert "raise ValueError" in result.patch
    assert result.final_patch_command.startswith("pyfixagent-apply --workspace")
    assert "--approve" not in result.final_patch_command
    assert (workspace / "calculator.py").read_text(encoding="utf-8") == original
    assert subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=workspace,
        check=True,
        capture_output=True,
        text=True,
    ).stdout == ""


def test_isolated_agent_rolls_back_regression_before_retry(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def add(a, b):\n    return a - b\n\n\ndef subtract(a, b):\n    return a - b\n",
        "from calculator import add, subtract\n\n"
        "def test_add():\n    assert add(2, 3) == 5\n\n"
        "def test_subtract():\n    assert subtract(5, 2) == 3\n",
    )
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace, check=True, capture_output=True)
    regression = (
        '[{"path":"calculator.py","old":"def add(a, b):\\n    return a - b\\n\\n\\n'
        'def subtract(a, b):\\n    return a - b\\n","new":"def add(a, b):\\n    return a + b\\n\\n\\n'
        'def subtract(a, b):\\n    return a + b\\n"}]'
    )
    repair = '[{"path":"calculator.py","old":"return a - b","new":"return a + b","start_line":2}]'
    agent = DefaultAgent(
        model=MockModel([regression, repair]),
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        max_iterations=2,
        require_clean_workspace=True,
        isolate_workspace=True,
    )

    result = agent.run("Fix tests.")

    assert result.success is True
    assert result.iterations[0].iteration_result["failure_type"] == "regression"
    assert result.iterations[0].workspace_action == "rolled_back_regression"
    assert result.iterations[1].workspace_action == "checkpointed_success"
    assert result.patch.count("+    return a + b") == 1
    assert (workspace / "calculator.py").read_text(encoding="utf-8").startswith(
        "def add(a, b):\n    return a - b"
    )


def test_isolated_agent_rolls_back_no_progress_and_expands_context(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def add(a, b):\n    return a - b\n",
        "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
    )
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace, check=True, capture_output=True)
    no_progress = '[{"path":"calculator.py","old":"return a - b","new":"return a * b"}]'
    repair = '[{"path":"calculator.py","old":"return a - b","new":"return a + b"}]'
    model = MockModel([no_progress, repair])
    agent = DefaultAgent(
        model=model,
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        max_iterations=2,
        require_clean_workspace=True,
        isolate_workspace=True,
        context_line_window=10,
        context_max_files=2,
    )

    result = agent.run("Fix tests.")

    assert result.success is True
    first, second = result.iterations
    assert first.iteration_result["failure_type"] == "no_progress"
    assert first.workspace_action == "rolled_back_no_progress"
    assert first.retry_reason == "rollback_no_progress_and_expand_context"
    assert first.context_expansion_level == 0
    assert second.context_expansion_level == 1
    assert second.context["expansion_level"] == 1
    assert second.context["effective_line_window"] == 20
    assert second.context["effective_max_files"] == 4
    assert "previous edit was rolled back" in model.prompts[1].lower()
    assert result.patch.count("+    return a + b") == 1
    assert (workspace / "calculator.py").read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a - b\n"
    )


def test_clean_workspace_guard_stops_before_pytest_and_model(tmp_path):
    workspace = init_workspace(
        tmp_path,
        "def add(a, b):\n    return a + b\n",
        "from calculator import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
    )
    model = MockModel([])
    agent = DefaultAgent(
        model=model,
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        require_clean_workspace=True,
    )

    result = agent.run("Fix tests.")

    assert result.success is False
    assert result.iterations == []
    assert result.workspace_strategy == "in_place_clean_guard"
    assert "no HEAD commit" in (result.error or "") or "uncommitted changes" in (result.error or "")
    assert model.calls == 0
