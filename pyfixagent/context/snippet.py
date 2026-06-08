from pathlib import Path


IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".git", "outputs", ".mypy_cache", ".ruff_cache"}


def resolve_python_path(workspace: Path, raw_path: str, include_tests: bool = True) -> Path | None:
    workspace = Path(workspace).resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = workspace / Path(raw_path.replace("\\", "/"))

    try:
        resolved = candidate.resolve()
        relative = resolved.relative_to(workspace)
    except (OSError, ValueError):
        return None

    if resolved.suffix != ".py":
        return None
    if not resolved.exists() or not resolved.is_file():
        return None
    if _is_ignored(relative):
        return None
    if not include_tests and relative.parts[:1] == ("tests",):
        return None
    return relative


def read_code_window(workspace: Path, relative_path: Path, target_lines: list[int], line_window: int) -> tuple[int, int, str]:
    target = Path(workspace).resolve() / relative_path
    lines = target.read_text(encoding="utf-8").splitlines()
    if not lines:
        return 1, 1, ""

    if not target_lines:
        start_line = 1
        end_line = len(lines)
    else:
        start_line = max(1, min(target_lines) - line_window)
        end_line = min(len(lines), max(target_lines) + line_window)

    content = "\n".join(lines[start_line - 1 : end_line])
    if content:
        content += "\n"
    return start_line, end_line, content


def iter_python_files(workspace: Path, include_tests: bool = True) -> list[Path]:
    workspace = Path(workspace).resolve()
    result: list[Path] = []
    for path in sorted(workspace.rglob("*.py")):
        try:
            relative = path.resolve().relative_to(workspace)
        except ValueError:
            continue
        if _is_ignored(relative):
            continue
        if not include_tests and relative.parts[:1] == ("tests",):
            continue
        result.append(relative)
    return result


def _is_ignored(relative: Path) -> bool:
    return any(part in IGNORED_DIRS or part.startswith(".") for part in relative.parts)
