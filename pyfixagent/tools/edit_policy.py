from dataclasses import dataclass
from pathlib import PurePosixPath
import re


@dataclass(frozen=True)
class EditPolicy:
    """Tool-enforced limits for model-generated edits."""

    allowed_paths: tuple[str, ...] = ()
    forbidden_path_parts: tuple[str, ...] = ("tests",)
    allowed_suffixes: tuple[str, ...] = (".py",)
    max_files: int = 8
    max_changed_lines: int = 400

    def validate_paths(self, paths: list[str]) -> str | None:
        normalized = list(dict.fromkeys(_normalize_path(path) for path in paths))
        if len(normalized) > self.max_files:
            return f"edit modifies {len(normalized)} files; maximum is {self.max_files}"

        allowed = tuple(_normalize_prefix(path) for path in self.allowed_paths)
        for path in normalized:
            candidate = PurePosixPath(path)
            if candidate.is_absolute() or ".." in candidate.parts or ".git" in candidate.parts:
                return f"edit path escapes workspace or is unsafe: {path}"
            if candidate.suffix not in self.allowed_suffixes:
                return f"edit target must be a .py file or another allowed suffix: {path}"
            if any(part in self.forbidden_path_parts for part in candidate.parts):
                return f"edit target is under a forbidden path: {path}"
            if allowed and not any(path == prefix or path.startswith(f"{prefix}/") for prefix in allowed):
                return f"edit target is outside allowed paths: {path}"
        return None

    def validate_changed_lines(self, changed_lines: int) -> str | None:
        if changed_lines > self.max_changed_lines:
            return f"edit changes about {changed_lines} lines; maximum is {self.max_changed_lines}"
        return None


def paths_from_patch(patch: str) -> list[str]:
    paths: list[str] = []
    for line in patch.splitlines():
        match = re.match(r"^diff --git (\S+) (\S+)$", line)
        if not match:
            continue
        path = match.group(2)
        if path.startswith("b/"):
            path = path[2:]
        paths.append(_normalize_path(path))
    return list(dict.fromkeys(paths))


def changed_lines_from_patch(patch: str) -> int:
    return sum(
        1
        for line in patch.splitlines()
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    )


def _normalize_path(path: str) -> str:
    value = path.replace("\\", "/")
    if value.startswith(("a/", "b/")):
        value = value[2:]
    return value.strip("/")


def _normalize_prefix(path: str) -> str:
    return _normalize_path(path).rstrip("/")
