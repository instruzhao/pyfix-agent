from pathlib import Path

from pyfixagent.context.provider import ContextProvider
from pyfixagent.context.policy import ContextExpansionPolicy
from pyfixagent.context.repository import RepositoryContextExpander
from pyfixagent.core.contracts import RepairRequest
from pyfixagent.core.engine import RepairEngine
from pyfixagent.execution.test_runner import TestRunner
from pyfixagent.execution.test_policy import normalize_test_commands
from pyfixagent.execution.workspace_session import WorkspaceSession
from pyfixagent.models.base import BaseModel
from pyfixagent.repair.backends.patch import PatchBackend
from pyfixagent.repair.backends.replacement import ReplacementBackend
from pyfixagent.repair.evaluator import AttemptEvaluator
from pyfixagent.repair.model_client import ModelClient
from pyfixagent.repair.prompting import PromptBuilder
from pyfixagent.repair.retry_policy import RetryPolicy
from pyfixagent.review.context import ReviewContextProvider
from pyfixagent.review.parser import ReviewParser
from pyfixagent.review.policy import ReviewPolicy
from pyfixagent.review.reviewer import SemanticReviewer
from pyfixagent.repository.cache import RepositoryIndexStore
from pyfixagent.repository.indexer import RepositoryIndexer
from pyfixagent.repository.service import RepositoryIndexService
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.schemas import AgentResult
from pyfixagent.tools.edit_policy import EditPolicy


class DefaultAgent:
    """Backward-compatible facade that assembles focused repair components."""

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
        context_max_expansion_level: int = 2,
        context_fallback_to_full: bool = True,
        context_include_tests: bool = True,
        require_clean_workspace: bool = False,
        allowed_paths: list[str] | tuple[str, ...] | None = None,
        max_changed_files: int = 8,
        max_changed_lines: int = 400,
        isolate_workspace: bool = False,
        test_commands: list[list[str]] | tuple[tuple[str, ...], ...] | None = None,
        semantic_review_enabled: bool = False,
        semantic_review_max_revisions: int = 1,
        semantic_review_parse_retries: int = 1,
        semantic_review_max_context_chars: int = 16000,
        semantic_review_max_feedback_chars: int = 3000,
        semantic_review_max_risks: int = 5,
        semantic_review_max_contracts: int = 3,
        review_model: BaseModel | None = None,
        repository_context_enabled: bool = False,
        repository_cache_dir: Path | None = None,
        repository_max_files: int = 2000,
        repository_max_file_bytes: int = 1_000_000,
        repository_max_graph_depth: int = 2,
        repository_max_related_files: int = 6,
        repository_max_snippet_lines: int = 200,
        context_max_selected_tokens: int = 12000,
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
        self.context_max_expansion_level = max(0, context_max_expansion_level)
        self.context_fallback_to_full = context_fallback_to_full
        self.context_include_tests = context_include_tests
        self.require_clean_workspace = require_clean_workspace
        self.isolate_workspace = isolate_workspace
        self.test_commands = normalize_test_commands(
            [list(command) for command in test_commands] if test_commands is not None else None
        )
        self.semantic_review_enabled = semantic_review_enabled
        self.semantic_review_max_revisions = max(0, semantic_review_max_revisions)
        self.semantic_review_parse_retries = max(0, semantic_review_parse_retries)
        self.semantic_review_max_context_chars = max(1000, semantic_review_max_context_chars)
        self.semantic_review_max_feedback_chars = max(200, semantic_review_max_feedback_chars)
        self.semantic_review_max_risks = max(1, semantic_review_max_risks)
        self.semantic_review_max_contracts = max(1, semantic_review_max_contracts)
        self.review_model = review_model
        self.repository_context_enabled = repository_context_enabled
        self.repository_cache_dir = (
            Path(repository_cache_dir)
            if repository_cache_dir is not None
            else self.patch_output_dir.parent / "index"
        )
        self.repository_max_files = max(1, repository_max_files)
        self.repository_max_file_bytes = max(1, repository_max_file_bytes)
        self.repository_max_graph_depth = max(0, repository_max_graph_depth)
        self.repository_max_related_files = max(0, repository_max_related_files)
        self.repository_max_snippet_lines = max(20, repository_max_snippet_lines)
        self.context_max_selected_tokens = max(100, context_max_selected_tokens)
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
        model_client = ModelClient(self.model)
        review_model_client = ModelClient(self.review_model or self.model)
        repository_expander = self._build_repository_expander()
        return RepairEngine(
            workspace_session=WorkspaceSession(
                self.sandbox.workspace,
                self.patch_output_dir,
                require_clean=self.require_clean_workspace,
                isolate=self.isolate_workspace,
            ),
            test_runner=TestRunner(self.sandbox, commands=self.test_commands),
            context_provider=ContextProvider(
                strategy=self.context_strategy,
                line_window=self.context_line_window,
                max_files=self.context_max_files,
                fallback_to_full=self.context_fallback_to_full,
                include_tests=self.context_include_tests,
                repository_expander=repository_expander,
            ),
            context_policy=ContextExpansionPolicy(self.context_max_expansion_level),
            prompt_builder=PromptBuilder(),
            model_client=model_client,
            backends={
                "patch": PatchBackend(self.edit_policy),
                "replacement": ReplacementBackend(self.edit_policy),
            },
            evaluator=AttemptEvaluator(),
            retry_policy=RetryPolicy(self.initial_mode),
            semantic_review_enabled=self.semantic_review_enabled,
            review_context_provider=ReviewContextProvider(
                max_chars=self.semantic_review_max_context_chars,
                include_tests=self.context_include_tests,
                repository_expander=repository_expander,
            ),
            semantic_reviewer=SemanticReviewer(
                review_model_client,
                ReviewParser(
                    max_risks=self.semantic_review_max_risks,
                    max_text_chars=self.semantic_review_max_feedback_chars,
                    max_contracts=self.semantic_review_max_contracts,
                ),
                max_parse_retries=self.semantic_review_parse_retries,
            ),
            review_policy=ReviewPolicy(self.semantic_review_max_revisions),
            review_max_feedback_chars=self.semantic_review_max_feedback_chars,
        )

    def _build_repository_expander(self) -> RepositoryContextExpander | None:
        if not self.repository_context_enabled:
            return None
        service = RepositoryIndexService(
            RepositoryIndexer(
                include_tests=self.context_include_tests,
                max_files=self.repository_max_files,
                max_file_bytes=self.repository_max_file_bytes,
            ),
            RepositoryIndexStore(self.repository_cache_dir),
        )
        return RepositoryContextExpander(
            service,
            max_selected_tokens=self.context_max_selected_tokens,
            max_graph_depth=self.repository_max_graph_depth,
            max_related_files=self.repository_max_related_files,
            max_snippet_lines=self.repository_max_snippet_lines,
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
            repository_expander=self._build_repository_expander(),
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
