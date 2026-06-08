from pathlib import Path


IGNORED_DIRS = {"__pycache__", ".pytest_cache", ".git", "outputs", ".mypy_cache", ".ruff_cache"}


def _is_ignored(path: Path) -> bool:
    return any(part in IGNORED_DIRS for part in path.parts)


def list_files(workspace: Path) -> str:
    workspace = Path(workspace)
    try:
        if not workspace.exists():
            raise FileNotFoundError(f"workspace does not exist: {workspace}")

        lines: list[str] = []
        for path in sorted(workspace.rglob("*")):
            rel = path.relative_to(workspace)
            if _is_ignored(rel):
                continue
            suffix = "/" if path.is_dir() else ""
            lines.append(f"{rel.as_posix()}{suffix}")
        return "\n".join(lines)
    except Exception as exc:
        raise RuntimeError(f"failed to list files in {workspace}: {exc}") from exc


def read_python_files(workspace: Path) -> str:
    workspace = Path(workspace)
    try:
        if not workspace.exists():
            raise FileNotFoundError(f"workspace does not exist: {workspace}")

        sections: list[str] = []
        for path in sorted(workspace.rglob("*.py")):
            rel = path.relative_to(workspace)
            if _is_ignored(rel):
                continue
            content = path.read_text(encoding="utf-8")
            sections.append(f"--- {rel.as_posix()} ---\n{content}")
        return "\n\n".join(sections)
    except Exception as exc:
        raise RuntimeError(f"failed to read Python files in {workspace}: {exc}") from exc
