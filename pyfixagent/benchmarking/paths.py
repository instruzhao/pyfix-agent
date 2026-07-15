from pathlib import Path


def existing_directory(root: Path, value, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a project-relative directory")
    path = inside_root(root, root / value)
    if not path.is_dir():
        raise ValueError(f"{label} does not exist: {path}")
    return path


def inside_root(root: Path, path: Path) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"benchmark path escapes project root: {path}") from exc
    return resolved


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def resolve(root: Path, path: str | Path) -> Path:
    candidate = Path(path)
    return candidate if candidate.is_absolute() else root / candidate
