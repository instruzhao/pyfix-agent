"""Validate the reviewed runner profiles against their declared CPython base."""

from __future__ import annotations

import json
from pathlib import Path
import re
import sys


_BASE_PYTHON = re.compile(r"^FROM\s+python:(\d+\.\d+)-", re.MULTILINE)
_CPYTHON_TAG = re.compile(r"\bcp(\d{2,3})\b")


def validate_runner_locks(project_root: Path) -> list[str]:
    dockerfile = (project_root / "containers" / "Dockerfile").read_text(encoding="utf-8")
    base_match = _BASE_PYTHON.search(dockerfile)
    if base_match is None:
        return ["containers/Dockerfile must declare a python:<major>.<minor> base image"]
    base_python = base_match.group(1)
    profile_manifest = json.loads(
        (project_root / "containers" / "profiles.json").read_text(encoding="utf-8")
    )
    errors: list[str] = []
    if profile_manifest.get("python") != base_python:
        errors.append(
            "containers/profiles.json python must match the Dockerfile base: "
            f"{profile_manifest.get('python')!r} != {base_python!r}"
        )
    expected_tag = "cp" + base_python.replace(".", "")
    for profile_name, profile in profile_manifest.get("profiles", {}).items():
        lock = project_root / profile["lock"]
        errors.extend(_validate_lock(profile_name, lock, expected_tag))
    return errors


def _validate_lock(profile_name: str, lock_path: Path, expected_tag: str) -> list[str]:
    if not lock_path.is_file():
        return [f"{profile_name}: lock file does not exist: {lock_path}"]
    lines = [
        line.strip()
        for line in lock_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    errors: list[str] = []
    if not lines:
        errors.append(f"{profile_name}: lock file is empty")
    if any(" --hash=sha256:" not in line for line in lines):
        errors.append(f"{profile_name}: every resolved requirement must include a SHA-256 hash")
    tags = {f"cp{tag}" for tag in _CPYTHON_TAG.findall("\n".join(lines))}
    incompatible = sorted(tag for tag in tags if tag != expected_tag)
    if incompatible:
        errors.append(
            f"{profile_name}: lock contains incompatible CPython wheel tags {incompatible}; expected {expected_tag}"
        )
    return errors


def main() -> int:
    project_root = Path(__file__).resolve().parents[1]
    errors = validate_runner_locks(project_root)
    if errors:
        print("runner lock validation failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("runner lock validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
