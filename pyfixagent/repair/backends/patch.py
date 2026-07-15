from pathlib import Path

from pyfixagent.core.contracts import ApplyResult
from pyfixagent.tools.edit_policy import EditPolicy
from pyfixagent.tools.patch_tools import (
    apply_patch,
    check_patch,
    clean_patch_text,
    get_git_diff,
    save_patch,
)


class PatchBackend:
    mode = "patch"

    def __init__(self, policy: EditPolicy):
        self.policy = policy

    def apply(self, workspace: Path, raw_output: str, patch_path: Path) -> ApplyResult:
        cleaned = clean_patch_text(raw_output)
        save_patch(workspace, cleaned, patch_path)
        checked = check_patch(workspace, cleaned, policy=self.policy)
        if not checked.success:
            error = checked.error or checked.stderr
            return ApplyResult(
                mode="patch",
                success=False,
                raw_output=raw_output,
                cleaned_patch=cleaned,
                patch_path=str(patch_path),
                check_error=error,
                command="git apply --check -",
                error=error,
                failure_stage="check",
            )

        applied = apply_patch(workspace, cleaned, policy=self.policy)
        if not applied.success:
            error = applied.error or applied.stderr
            return ApplyResult(
                mode="patch",
                success=False,
                raw_output=raw_output,
                cleaned_patch=cleaned,
                patch_path=str(patch_path),
                check_success=True,
                apply_error=error,
                command="git apply -",
                error=error,
                failure_stage="apply",
            )

        diff = get_git_diff(workspace)
        if not diff.success:
            error = diff.error or "git diff failed"
            return ApplyResult(
                mode="patch",
                success=False,
                raw_output=raw_output,
                cleaned_patch=cleaned,
                patch_path=str(patch_path),
                check_success=True,
                apply_success=True,
                apply_error=error,
                command="git diff --",
                error=error,
                failure_stage="diff",
                applied_to_workspace=True,
            )

        save_patch(workspace, diff.stdout, patch_path)
        return ApplyResult(
            mode="patch",
            success=True,
            raw_output=raw_output,
            cleaned_patch=diff.stdout,
            patch_path=str(patch_path),
            check_success=True,
            apply_success=True,
            command="git diff --",
            applied_to_workspace=True,
        )
