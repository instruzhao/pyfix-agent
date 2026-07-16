import subprocess

import pytest

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.context.policy import ContextExpansionPolicy
from pyfixagent.benchmark import run_benchmark as facade_run_benchmark
from pyfixagent.benchmarking.runner import run_benchmark as modular_run_benchmark
from pyfixagent.core.contracts import ApplyResult
from pyfixagent.models.base import BaseModel
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.models.mock_model import MockModel
from pyfixagent.repair.backends.patch import PatchBackend
from pyfixagent.repair.backends.replacement import ReplacementBackend
from pyfixagent.repair.model_client import ModelClient, ModelGenerationError
from pyfixagent.repair.retry_policy import RetryPolicy
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.tools.edit_policy import EditPolicy


def init_git_workspace(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    return workspace


def test_patch_backend_owns_patch_validation_and_application(tmp_path):
    workspace = init_git_workspace(tmp_path)
    patch_path = tmp_path / "patches" / "attempt.patch"
    raw_patch = """--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""

    result = PatchBackend(EditPolicy()).apply(workspace, raw_patch, patch_path)

    assert result.success is True
    assert result.check_success is True
    assert result.apply_success is True
    assert result.command == "git diff --"
    assert result.cleaned_patch.startswith("diff --git a/calculator.py b/calculator.py")
    assert "return a + b" in (workspace / "calculator.py").read_text(encoding="utf-8")


def test_replacement_backend_reports_parse_failure_without_writing(tmp_path):
    workspace = init_git_workspace(tmp_path)
    original = (workspace / "calculator.py").read_text(encoding="utf-8")

    result = ReplacementBackend(EditPolicy()).apply(
        workspace,
        "not replacement json",
        tmp_path / "attempt.patch",
    )

    assert result.success is False
    assert result.failure_stage == "parse"
    assert result.replacement_success is False
    assert (workspace / "calculator.py").read_text(encoding="utf-8") == original


def test_retry_policy_is_the_only_mode_switch_owner():
    policy = RetryPolicy("patch")
    failed_check = ApplyResult(
        mode="patch",
        success=False,
        raw_output="bad patch",
        failure_stage="check",
    )

    first = policy.after_apply(failed_check)
    second = policy.after_apply(failed_check)

    assert first.next_mode == "patch"
    assert second.next_mode == "replacement"
    assert policy.mode == "replacement"


def test_retry_policy_switches_backend_after_repeated_replacement_apply_failures():
    policy = RetryPolicy("replacement")
    failed_apply = ApplyResult(
        mode="replacement",
        success=False,
        raw_output="[]",
        failure_stage="apply",
    )

    first = policy.after_apply(failed_apply)
    second = policy.after_apply(failed_apply)

    assert first.next_mode == "replacement"
    assert second.next_mode == "patch"
    assert second.reason == "switch_to_patch_after_replacement_apply_failures"


def test_retry_policy_switches_immediately_when_replacement_loses_source_anchor():
    policy = RetryPolicy("replacement")
    result = ApplyResult(
        mode="replacement",
        success=False,
        raw_output="[]",
        failure_stage="apply",
        error="old text was not found exactly once in src/app.py",
    )

    decision = policy.after_apply(result)

    assert decision.next_mode == "patch"
    assert decision.reason == "switch_to_patch_after_lost_replacement_anchor"


def test_retry_policy_maps_failure_delta_outcomes_to_workspace_actions():
    policy = RetryPolicy("replacement")

    no_progress = policy.after_test_failure({"failure_type": "no_progress"})
    partial = policy.after_test_failure({"failure_type": "incomplete_fix"})
    regression = policy.after_test_failure({"failure_type": "regression"})

    assert no_progress.rollback is True
    assert no_progress.expand_context is True
    assert partial.checkpoint is True
    assert partial.rollback is False
    assert regression.rollback is True
    assert regression.reason == "rollback_regression_and_expand_context"


def test_context_expansion_policy_widens_then_uses_full_context():
    policy = ContextExpansionPolicy()

    initial = policy.plan(strategy="traceback", line_window=20, max_files=3, allow_full=True)
    policy.expand("no_progress")
    widened = policy.plan(strategy="traceback", line_window=20, max_files=3, allow_full=True)
    policy.expand("no_progress")
    full = policy.plan(strategy="traceback", line_window=20, max_files=3, allow_full=True)

    assert (initial.strategy, initial.line_window, initial.max_files, initial.level) == (
        "traceback",
        20,
        3,
        0,
    )
    assert (widened.strategy, widened.line_window, widened.max_files, widened.level) == (
        "traceback",
        40,
        6,
        1,
    )
    assert full.strategy == "full"
    assert full.level == 2


class FailingModel(BaseModel):
    def generate_patch(self, system_prompt: str, user_prompt: str) -> str:
        raise RuntimeError("provider unavailable")


def test_model_client_normalizes_model_errors_with_metadata():
    client = ModelClient(FailingModel())

    with pytest.raises(ModelGenerationError, match="provider unavailable") as raised:
        client.generate("system", "user")

    assert raised.value.metadata["duration_seconds"] is not None
    assert raised.value.metadata["model"] == "FailingModel"


def test_litellm_model_can_merge_system_contract_into_user_message():
    model = LiteLLMModel("openai/example", system_prompt_as_user=True)

    messages = model._messages("system contract", "repair prompt")

    assert messages == [
        {
            "role": "user",
            "content": "Agent output contract:\nsystem contract\n\nRepair request:\nrepair prompt",
        }
    ]


def test_default_agent_is_a_component_assembly_facade(tmp_path):
    workspace = init_git_workspace(tmp_path)
    agent = DefaultAgent(
        model=MockModel([]),
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
    )

    engine = agent._build_engine()

    assert isinstance(engine.backends["patch"], PatchBackend)
    assert isinstance(engine.backends["replacement"], ReplacementBackend)
    assert engine.test_runner.sandbox is agent.sandbox


def test_benchmark_module_remains_a_compatibility_facade():
    assert facade_run_benchmark is modular_run_benchmark
