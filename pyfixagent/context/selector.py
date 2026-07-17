from collections import OrderedDict
from dataclasses import dataclass
import ast
from pathlib import Path

from pyfixagent.context.snippet import iter_python_files, read_code_window, resolve_python_path
from pyfixagent.context.traceback_parser import PytestFailureSummary


@dataclass
class SelectedSnippet:
    path: str
    reason: str
    start_line: int
    end_line: int
    content: str
    score: float | None = None
    graph_distance: int | None = None
    symbol: str | None = None


@dataclass
class SelectedContext:
    strategy: str
    snippets: list[SelectedSnippet]
    fallback_used: bool
    prompt_chars: int | None = None
    repository_metadata: dict | None = None


def select_context(
    summary: PytestFailureSummary,
    workspace: Path,
    strategy: str = "traceback",
    line_window: int = 40,
    max_files: int = 6,
    fallback_to_full_context: bool = True,
    include_tests: bool = True,
) -> SelectedContext:
    if strategy not in {"full", "traceback"}:
        raise ValueError("context strategy must be 'full' or 'traceback'")

    if strategy == "full":
        return _select_full_context(workspace, include_tests=include_tests)

    candidates: OrderedDict[str, dict[str, object]] = OrderedDict()

    frame_lines_by_path: dict[str, list[int]] = {}
    for frame in summary.frames:
        relative = resolve_python_path(workspace, frame.path, include_tests=include_tests)
        if relative is None:
            continue
        key = relative.as_posix()
        frame_lines_by_path.setdefault(key, [])
        if frame.line is not None:
            frame_lines_by_path[key].append(frame.line)

    for node in summary.failed_tests:
        test_path = node.split("::", 1)[0]
        relative = resolve_python_path(workspace, test_path, include_tests=include_tests)
        if relative is None:
            continue
        key = relative.as_posix()
        _add_candidate(candidates, key, "failing_test_file", frame_lines_by_path.get(key, []))

    for frame in summary.frames:
        relative = resolve_python_path(workspace, frame.path, include_tests=include_tests)
        if relative is None:
            continue
        key = relative.as_posix()
        line_numbers = [frame.line] if frame.line is not None else []
        _add_candidate(candidates, key, "traceback_source_file", line_numbers)

    for node in summary.failed_tests:
        test_path = node.split("::", 1)[0]
        relative = resolve_python_path(workspace, test_path, include_tests=include_tests)
        if relative is None:
            continue
        for imported in _infer_imported_workspace_modules(workspace, relative, include_tests=include_tests):
            key = imported.as_posix()
            _add_candidate(candidates, key, "direct_test_import", [])

    snippets = _build_snippets(workspace, candidates, line_window=line_window, max_files=max_files)
    if snippets:
        return SelectedContext(strategy="traceback", snippets=snippets, fallback_used=False)

    if fallback_to_full_context:
        fallback = _select_full_context(workspace, include_tests=include_tests)
        fallback.strategy = "traceback"
        fallback.fallback_used = True
        return fallback

    return SelectedContext(strategy="traceback", snippets=[], fallback_used=False)


def _add_candidate(
    candidates: OrderedDict[str, dict[str, object]],
    path: str,
    reason: str,
    line_numbers: list[int],
) -> None:
    if path not in candidates:
        candidates[path] = {"reason": reason, "line_numbers": []}

    current = candidates[path]
    current_lines = current["line_numbers"]
    assert isinstance(current_lines, list)
    for line in line_numbers:
        if line not in current_lines:
            current_lines.append(line)


def _build_snippets(
    workspace: Path,
    candidates: OrderedDict[str, dict[str, object]],
    line_window: int,
    max_files: int,
) -> list[SelectedSnippet]:
    snippets: list[SelectedSnippet] = []
    for path, data in candidates.items():
        if len(snippets) >= max_files:
            break
        relative = Path(path)
        line_numbers = data["line_numbers"]
        assert isinstance(line_numbers, list)
        try:
            start_line, end_line, content = read_code_window(workspace, relative, line_numbers, line_window)
        except OSError:
            continue
        snippets.append(
            SelectedSnippet(
                path=path,
                reason=str(data["reason"]),
                start_line=start_line,
                end_line=end_line,
                content=content,
            )
        )
    return snippets


def _infer_imported_workspace_modules(workspace: Path, test_relative_path: Path, include_tests: bool) -> list[Path]:
    test_path = Path(workspace).resolve() / test_relative_path
    try:
        tree = ast.parse(test_path.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []

    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            modules.append(node.module)
            modules.extend(f"{node.module}.{alias.name}" for alias in node.names)

    inferred: list[Path] = []
    for module in modules:
        module_path = module.replace(".", "/")
        for raw_path in (f"{module_path}.py", f"{module_path}/__init__.py"):
            relative = resolve_python_path(workspace, raw_path, include_tests=include_tests)
            if relative is not None and relative != test_relative_path and relative not in inferred:
                inferred.append(relative)
    return inferred


def _select_full_context(workspace: Path, include_tests: bool = True) -> SelectedContext:
    snippets: list[SelectedSnippet] = []
    for relative in iter_python_files(workspace, include_tests=include_tests):
        start_line, end_line, content = read_code_window(workspace, relative, [], line_window=0)
        snippets.append(
            SelectedSnippet(
                path=relative.as_posix(),
                reason="fallback_full_context",
                start_line=start_line,
                end_line=end_line,
                content=content,
            )
        )
    return SelectedContext(strategy="full", snippets=snippets, fallback_used=False)
