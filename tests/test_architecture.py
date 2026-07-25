import ast
import inspect
from pathlib import Path
import subprocess

import pytest

import pyfixagent.benchmarking.metrics as metrics_module
import pyfixagent.benchmarking.runner as runner_module
import pyfixagent.main as main_module
from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.context.policy import ContextExpansionPolicy
from pyfixagent.benchmark import run_benchmark as facade_run_benchmark
from pyfixagent.benchmarking.runner import run_benchmark as modular_run_benchmark
from pyfixagent.core.contracts import ApplyResult
from pyfixagent.core.engine import EngineServices, RepairEngine
from pyfixagent.models.base import BaseModel
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.models.mock_model import MockModel
from pyfixagent.repair.backends.patch import PatchBackend
from pyfixagent.repair.backends.replacement import ReplacementBackend
from pyfixagent.repair.model_client import ModelClient, ModelGenerationError
from pyfixagent.repair.retry_policy import RetryPolicy
from pyfixagent.context.repository import RepositoryContextExpander
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.sandbox.container_sandbox import ContainerSandbox
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


def test_repair_engine_keeps_run_as_small_orchestrator(tmp_path):
    workspace = init_git_workspace(tmp_path)
    agent = DefaultAgent(
        model=MockModel([]),
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
    )
    engine = agent._build_engine()
    source = inspect.getsource(RepairEngine)
    tree = ast.parse(source)
    repair_engine = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    methods = {
        node.name: node
        for node in repair_engine.body
        if isinstance(node, ast.FunctionDef)
    }

    assert isinstance(engine.services, EngineServices)
    assert len(inspect.signature(RepairEngine.__init__).parameters) == 2
    assert methods["run"].end_lineno - methods["run"].lineno + 1 <= 35
    assert {
        "_prepare",
        "_plan_and_generate",
        "_apply",
        "_verify",
        "_accept_or_retry",
        "_run_semantic_review",
        "_record_review",
        "_apply_review_decision",
        "_close_workspace",
    } <= methods.keys()
    assert max(method.end_lineno - method.lineno + 1 for method in methods.values()) <= 65
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        for node in ast.walk(repair_engine)
    )


def test_other_orchestration_entrypoints_stay_small_and_delegated():
    runner_tree = ast.parse(inspect.getsource(runner_module))
    main_tree = ast.parse(inspect.getsource(main_module))
    metrics_tree = ast.parse(inspect.getsource(metrics_module))
    container_tree = ast.parse(inspect.getsource(ContainerSandbox))

    runner_functions = _function_nodes(runner_tree)
    main_functions = _function_nodes(main_tree)
    metrics_functions = _function_nodes(metrics_tree)
    container_class = next(node for node in container_tree.body if isinstance(node, ast.ClassDef))
    container_functions = {
        node.name: node for node in container_class.body if isinstance(node, ast.FunctionDef)
    }
    runner_class = next(node for node in runner_tree.body if isinstance(node, ast.ClassDef) and node.name == "BenchmarkRunner")
    runner_methods = [node for node in runner_class.body if isinstance(node, ast.FunctionDef)]

    assert _line_count(runner_functions["run_benchmark"]) <= 20
    assert _line_count(runner_functions["build_run_record"]) <= 35
    assert _line_count(main_functions["resolve_runtime_config"]) <= 20
    assert _line_count(main_functions["main"]) <= 25
    assert _line_count(metrics_functions["summarize_runs"]) <= 15
    assert _line_count(container_functions["run"]) <= 25
    assert max(_line_count(method) for method in runner_methods) <= 65
    assert max(_line_count(function) for function in runner_functions.values()) <= 65
    assert max(_line_count(function) for function in main_functions.values()) <= 65
    assert max(_line_count(function) for function in metrics_functions.values()) <= 65
    assert max(_line_count(function) for function in container_functions.values()) <= 65
    assert {"_run_variant", "_run_prepared_workspace", "_cleanup_variant"} <= {
        method.name for method in runner_methods
    }


def test_broad_exception_boundaries_are_explicit_and_stack_logged():
    root = Path(__file__).resolve().parents[1]
    expected = {
        ("benchmarking/runner.py", "_run_variant"),
        ("models/litellm_model.py", "generate_patch"),
        ("repair/model_client.py", "generate"),
        ("sandbox/bounded_process.py", "run_bounded_process"),
    }
    found: set[tuple[str, str]] = set()
    for path in (root / "pyfixagent").rglob("*.py"):
        relative = path.relative_to(root / "pyfixagent").as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
            for handler in (node for node in ast.walk(function) if isinstance(node, ast.ExceptHandler)):
                if not isinstance(handler.type, ast.Name) or handler.type.id != "Exception":
                    continue
                found.add((relative, function.name))
                assert any(
                    isinstance(call, ast.Call)
                    and isinstance(call.func, ast.Attribute)
                    and isinstance(call.func.value, ast.Name)
                    and call.func.value.id == "logger"
                    and call.func.attr == "exception"
                    for call in ast.walk(handler)
                )
    assert found == expected


def test_print_calls_are_limited_to_cli_or_human_facing_output():
    root = Path(__file__).resolve().parents[1]
    allowed = {
        "pyfixagent/apply.py",
        "pyfixagent/benchmarking/cli.py",
        "pyfixagent/benchmarking/compare_cli.py",
        "pyfixagent/container_benchmark.py",
        "pyfixagent/container_security.py",
        "pyfixagent/trace_viewer.py",
        "scripts/reset_demo.py",
        "scripts/summarize_trace.py",
        "scripts/validate_runner_locks.py",
    }
    paths_with_prints = set()
    for base in (root / "pyfixagent", root / "scripts"):
        for path in base.rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            if any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "print"
                for node in ast.walk(tree)
            ):
                paths_with_prints.add(path.relative_to(root).as_posix())
    assert paths_with_prints == allowed


def _function_nodes(tree: ast.AST) -> dict[str, ast.FunctionDef]:
    return {
        node.name: node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
    }


def _line_count(node: ast.FunctionDef) -> int:
    return node.end_lineno - node.lineno + 1


def test_default_agent_assembles_one_shared_repository_context_service(tmp_path):
    workspace = init_git_workspace(tmp_path)
    agent = DefaultAgent(
        model=MockModel([]),
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
        repository_context_enabled=True,
        repository_cache_dir=tmp_path / "index",
    )

    engine = agent._build_engine()

    repair_expander = engine.context_provider.repository_expander
    review_expander = engine.review_context_provider.repository_expander
    assert isinstance(repair_expander, RepositoryContextExpander)
    assert repair_expander is review_expander


def test_default_agent_can_use_a_separate_bounded_review_model(tmp_path):
    workspace = init_git_workspace(tmp_path)
    repair_model = MockModel([])
    review_model = MockModel([])
    agent = DefaultAgent(
        model=repair_model,
        review_model=review_model,
        sandbox=LocalSandbox(workspace),
        patch_output_dir=tmp_path / "patches",
    )

    engine = agent._build_engine()

    assert engine.model_client.model is repair_model
    assert engine.semantic_reviewer.model_client.model is review_model


def test_benchmark_module_remains_a_compatibility_facade():
    assert facade_run_benchmark is modular_run_benchmark
