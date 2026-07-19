from __future__ import annotations

from hashlib import sha256
import platform
from pathlib import Path
import subprocess
import sys


def build_protocol_metadata(
    *,
    project_root: Path,
    manifest_path: Path,
    config_path: Path,
    case_ids: list[str],
    repeat: int,
    strategies: list[str],
    repository_modes: list[str],
    trace_redaction: str,
    model_name: str,
    review_model_name: str,
    sandbox_backend: str,
    container_engine: str | None,
    container_image: str | None,
) -> dict:
    """Build a secret-free, reproducible description of one benchmark protocol."""
    revision = _git_output(project_root, "rev-parse", "HEAD")
    dirty = bool(_git_output(project_root, "status", "--porcelain"))
    return {
        "protocol_version": 1,
        "project_revision": revision or None,
        "project_dirty": dirty,
        "manifest_path": _relative_path(manifest_path, project_root),
        "manifest_sha256": _file_digest(manifest_path),
        "config_path": _relative_path(config_path, project_root),
        "config_sha256": _file_digest(config_path),
        "case_ids": sorted(case_ids),
        "case_count": len(case_ids),
        "repeat": repeat,
        "strategies": sorted(strategies),
        "repository_modes": sorted(set(repository_modes)),
        "trace_redaction": trace_redaction,
        "model": model_name,
        "review_model": review_model_name,
        "sandbox_backend": sandbox_backend,
        "container_engine": container_engine,
        "container_image": container_image,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "implementation": sys.implementation.name,
    }


def _file_digest(path: Path) -> str:
    return sha256(Path(path).read_bytes()).hexdigest()


def _relative_path(path: Path, root: Path) -> str:
    try:
        return Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return f"<external>/{Path(path).name}"


def _git_output(root: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            timeout=10,
            capture_output=True,
            text=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""
