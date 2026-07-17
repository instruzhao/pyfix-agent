from pathlib import Path

from pyfixagent.context.builder import context_trace_metadata, render_selected_context
from pyfixagent.context.policy import ContextPlan
from pyfixagent.context.repository import RepositoryContextExpander
from pyfixagent.context.selector import select_context
from pyfixagent.context.traceback_parser import parse_pytest_failure_output
from pyfixagent.core.contracts import ContextBundle
from pyfixagent.tools.file_tools import read_python_files


class ContextProvider:
    """Selects only the source context needed by the prompt."""

    def __init__(
        self,
        strategy: str = "traceback",
        line_window: int = 40,
        max_files: int = 6,
        fallback_to_full: bool = True,
        include_tests: bool = True,
        repository_expander: RepositoryContextExpander | None = None,
    ):
        if strategy not in {"full", "traceback"}:
            raise ValueError("context_strategy must be 'full' or 'traceback'")
        self.strategy = strategy
        self.line_window = max(0, line_window)
        self.max_files = max(1, max_files)
        self.fallback_to_full = fallback_to_full
        self.include_tests = include_tests
        self.repository_expander = repository_expander

    def build(
        self,
        workspace: Path,
        pytest_output: str,
        plan: ContextPlan | None = None,
    ) -> ContextBundle:
        effective = plan or ContextPlan(
            strategy=self.strategy,
            line_window=self.line_window,
            max_files=self.max_files,
            level=0,
        )
        summary = parse_pytest_failure_output(pytest_output)
        selected = select_context(
            summary=summary,
            workspace=workspace,
            strategy=effective.strategy,
            line_window=effective.line_window,
            max_files=effective.max_files,
            fallback_to_full_context=self.fallback_to_full,
            include_tests=self.include_tests,
        )
        if self.repository_expander is not None:
            selected = self.repository_expander.expand(workspace, selected, pytest_output)
        rendered = (
            read_python_files(workspace)
            if effective.strategy == "full" and self.repository_expander is None
            else render_selected_context(selected)
        )
        selected.prompt_chars = len(rendered)
        metadata = context_trace_metadata(selected)
        metadata["pytest_output_chars"] = len(pytest_output)
        metadata["stats"]["pytest_output_chars"] = len(pytest_output)
        metadata["failed_tests"] = summary.failed_tests
        metadata["exception_type"] = summary.exception_type
        metadata["error_message"] = summary.error_message
        metadata["raw_traceback_frames"] = [
            {"path": frame.path, "line": frame.line, "function": frame.function}
            for frame in summary.frames
        ]
        metadata["base_strategy"] = self.strategy
        metadata["expansion_level"] = effective.level
        metadata["effective_line_window"] = effective.line_window
        metadata["effective_max_files"] = effective.max_files
        return ContextBundle(rendered=rendered, metadata=metadata)
