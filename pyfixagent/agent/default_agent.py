from pathlib import Path

from pyfixagent.context.provider import ContextProvider
from pyfixagent.core.contracts import RepairRequest
from pyfixagent.core.engine import RepairEngine
from pyfixagent.execution.test_runner import TestRunner
from pyfixagent.execution.workspace_session import WorkspaceSession
from pyfixagent.models.base import BaseModel
from pyfixagent.repair.backends.patch import PatchBackend
from pyfixagent.repair.backends.replacement import ReplacementBackend
from pyfixagent.repair.evaluator import AttemptEvaluator
from pyfixagent.repair.model_client import ModelClient
from pyfixagent.repair.prompting import PromptBuilder
from pyfixagent.repair.retry_policy import RetryPolicy
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.schemas import AgentResult
from pyfixagent.tools.edit_policy import EditPolicy


class DefaultAgent:
    """Backward-compatible facade that assembles the v0.4 repair components."""

    def __init__(
        self,
        model: BaseModel,
        sandbox: LocalSandbox,
        patch_output_dir: Path,
        max_iterations: int = 1,
        initial_mode: str = "replacement",
        context_strategy: str = "traceback",
        context_line_window: int = 40,
        context_max_files: int = 6,
        context_fallback_to_full: bool = True,
        context_include_tests: bool = True,
        require_clean_workspace: bool = False,
        allowed_paths: list[str] | tuple[str, ...] | None = None,
        max_changed_files: int = 8,
        max_changed_lines: int = 400,
    ):
        if initial_mode not in {"patch", "replacement"}:
            raise ValueError("initial_mode must be 'patch' or 'replacement'")
        if context_strategy not in {"full", "traceback"}:
            raise ValueError("context_strategy must be 'full' or 'traceback'")
        self.model = model
        self.sandbox = sandbox
        self.patch_output_dir = Path(patch_output_dir)
        self.max_iterations = max(1, max_iterations)
        self.initial_mode = initial_mode
        self.context_strategy = context_strategy
        self.context_line_window = max(0, context_line_window)
        self.context_max_files = max(1, context_max_files)
        self.context_fallback_to_full = context_fallback_to_full
        self.context_include_tests = context_include_tests
        self.require_clean_workspace = require_clean_workspace
        self.edit_policy = EditPolicy(
            allowed_paths=tuple(allowed_paths or ()),
            max_files=max(1, max_changed_files),
            max_changed_lines=max(1, max_changed_lines),
        )

    def run(self, task: str) -> AgentResult:
        request = RepairRequest(
            task=task,
            workspace=self.sandbox.workspace,
            max_iterations=self.max_iterations,
        )
        return self._build_engine().run(request)

    def _build_engine(self) -> RepairEngine:
        return RepairEngine(
            workspace_session=WorkspaceSession(
                self.sandbox.workspace,
                self.patch_output_dir,
                require_clean=self.require_clean_workspace,
            ),
            test_runner=TestRunner(self.sandbox),
            context_provider=ContextProvider(
                strategy=self.context_strategy,
                line_window=self.context_line_window,
                max_files=self.context_max_files,
                fallback_to_full=self.context_fallback_to_full,
                include_tests=self.context_include_tests,
            ),
            prompt_builder=PromptBuilder(),
            model_client=ModelClient(self.model),
            backends={
                "patch": PatchBackend(self.edit_policy),
                "replacement": ReplacementBackend(self.edit_policy),
            },
            evaluator=AttemptEvaluator(),
            retry_policy=RetryPolicy(self.initial_mode),
        )

    @staticmethod
    def _format_test_output(result) -> str:
        return TestRunner.format_output(result)

    def _build_context_prompt(self, workspace: Path, pytest_output: str) -> tuple[str, dict]:
        bundle = ContextProvider(
            strategy=self.context_strategy,
            line_window=self.context_line_window,
            max_files=self.context_max_files,
            fallback_to_full=self.context_fallback_to_full,
            include_tests=self.context_include_tests,
        ).build(workspace, pytest_output)
        return bundle.rendered, bundle.metadata

    @staticmethod
    def _update_context_prompt_chars(context: dict, prompt_chars: int) -> None:
        context["prompt_chars"] = prompt_chars
        context.setdefault("stats", {})["prompt_chars"] = prompt_chars

    _patch_failure_feedback = staticmethod(PromptBuilder.patch_failure)
    _test_failure_feedback = staticmethod(PromptBuilder.patch_test_failure)
    _replacement_failure_feedback = staticmethod(PromptBuilder.replacement_failure)
    _replacement_test_failure_feedback = staticmethod(PromptBuilder.replacement_test_failure)
    _build_iteration_record = staticmethod(AttemptEvaluator.build_record)
    _replacement_edits_to_dicts = staticmethod(ReplacementBackend._serialize_edits)
