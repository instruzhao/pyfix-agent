from dataclasses import asdict
from pathlib import Path

from pyfixagent.core.contracts import ApplyResult
from pyfixagent.tools.edit_policy import EditPolicy
from pyfixagent.tools.patch_tools import get_git_diff, save_patch
from pyfixagent.tools.replacement_tools import apply_replacements, parse_replacements


class ReplacementBackend:
    mode = "replacement"

    def __init__(self, policy: EditPolicy):
        self.policy = policy

    def apply(self, workspace: Path, raw_output: str, patch_path: Path) -> ApplyResult:
        try:
            edits = parse_replacements(raw_output)
        except Exception as exc:
            error = str(exc)
            return ApplyResult(
                mode="replacement",
                success=False,
                raw_output=raw_output,
                error=error,
                failure_stage="parse",
                replacement_success=False,
                replacement_error=error,
            )

        serialized = self._serialize_edits(edits)
        applied = apply_replacements(workspace, edits, policy=self.policy)
        if not applied.success:
            error = applied.error or "replacement apply failed"
            return ApplyResult(
                mode="replacement",
                success=False,
                raw_output=raw_output,
                error=error,
                failure_stage="apply",
                replacement_edits=serialized,
                replacement_success=False,
                replacement_error=error,
            )

        diff = get_git_diff(workspace)
        if not diff.success:
            error = diff.error or "git diff failed"
            return ApplyResult(
                mode="replacement",
                success=False,
                raw_output=raw_output,
                apply_success=True,
                apply_error=error,
                command="git diff --",
                error=error,
                failure_stage="diff",
                applied_to_workspace=True,
                replacement_edits=serialized,
                replacement_success=True,
            )

        save_patch(workspace, diff.stdout, patch_path)
        return ApplyResult(
            mode="replacement",
            success=True,
            raw_output=raw_output,
            cleaned_patch=diff.stdout,
            patch_path=str(patch_path),
            apply_success=True,
            command="git diff --",
            applied_to_workspace=True,
            replacement_edits=serialized,
            replacement_success=True,
        )

    @staticmethod
    def _serialize_edits(edits) -> list[dict]:
        result: list[dict] = []
        for edit in edits:
            item = asdict(edit)
            if item.get("start_line") is None:
                item.pop("start_line", None)
            result.append(item)
        return result
