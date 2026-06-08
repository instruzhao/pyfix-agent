from pathlib import Path
import subprocess

from patch_eval.types import (
    CORRUPT_PATCH,
    GIT_APPLY_CHECK_FAILED,
    GitApplyResult,
    PATCH_CONTEXT_MISMATCH,
)


def run_git_apply_check(repo_path: Path, patch: str) -> GitApplyResult:
    completed = subprocess.run(
        ["git", "apply", "--check", "-"],
        input=patch.encode("utf-8"),
        cwd=Path(repo_path),
        capture_output=True,
        check=False,
    )
    stdout = completed.stdout.decode("utf-8", errors="replace")
    stderr = completed.stderr.decode("utf-8", errors="replace")
    if completed.returncode == 0:
        return GitApplyResult(
            ok=True,
            returncode=0,
            stdout=stdout,
            stderr=stderr,
            error_type=None,
        )

    return GitApplyResult(
        ok=False,
        returncode=completed.returncode,
        stdout=stdout,
        stderr=stderr,
        error_type=_classify_git_apply_error(stderr),
    )


def _classify_git_apply_error(stderr: str) -> str:
    lowered = stderr.lower()
    if "corrupt patch" in lowered:
        return CORRUPT_PATCH
    if "patch failed" in lowered or "does not apply" in lowered or "while searching for" in lowered:
        return PATCH_CONTEXT_MISMATCH
    return GIT_APPLY_CHECK_FAILED
