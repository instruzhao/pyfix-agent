from pathlib import Path
import time

from pyfixagent.context.pytest_summary import parse_pytest_summary, pytest_summary_to_dict
from pyfixagent.core.contracts import ApplyResult, EditProposal
from pyfixagent.schemas import IterationRecord
from pyfixagent.trace import (
    build_apply,
    build_model_output,
    edit_summary,
    failure_delta,
    iteration_result,
)


class AttemptEvaluator:
    """Turns raw attempt facts into the stable trace schema."""

    def model_error_record(
        self,
        *,
        iteration: int,
        prompt: str,
        patch_path: Path,
        started_at: float,
        mode: str,
        error: str,
        context: dict,
        test_summary_before: dict,
        model_call: dict,
    ) -> IterationRecord:
        return self.build_record(
            iteration=iteration,
            prompt=prompt,
            raw_model_output="",
            cleaned_patch="",
            patch_path="" if mode == "replacement" else patch_path,
            apply_check_success=False,
            apply_check_error="",
            apply_success=False,
            apply_error="" if mode == "replacement" else error,
            pytest_exit_code=None,
            pytest_output="",
            success=False,
            started_at=started_at,
            mode=mode,
            model_output_type=mode,
            replacement_raw_output="" if mode == "replacement" else None,
            replacement_success=False if mode == "replacement" else None,
            replacement_error=error if mode == "replacement" else None,
            context=context,
            test_summary_before=test_summary_before,
            model_call=model_call,
        )

    def apply_record(
        self,
        *,
        iteration: int,
        proposal: EditProposal,
        result: ApplyResult,
        started_at: float,
        context: dict,
        test_summary_before: dict,
        pytest_exit_code: int | None = None,
        pytest_output: str = "",
        success: bool = False,
    ) -> IterationRecord:
        return self.build_record(
            iteration=iteration,
            prompt=proposal.prompt,
            raw_model_output=proposal.raw_output,
            cleaned_patch=result.cleaned_patch,
            patch_path=result.patch_path,
            apply_check_success=result.check_success,
            apply_check_error=result.check_error,
            apply_success=result.apply_success,
            apply_error=result.apply_error,
            pytest_exit_code=pytest_exit_code,
            pytest_output=pytest_output,
            success=success,
            started_at=started_at,
            mode=result.mode,
            model_output_type=result.mode,
            replacement_raw_output=(proposal.raw_output if result.mode == "replacement" else None),
            replacement_edits=result.replacement_edits,
            replacement_success=result.replacement_success,
            replacement_error=result.replacement_error,
            patch_command=result.command,
            context=context,
            test_summary_before=test_summary_before,
            model_call=proposal.model_call,
        )

    @staticmethod
    def build_record(
        iteration: int,
        prompt: str,
        raw_model_output: str,
        cleaned_patch: str,
        patch_path: Path | str,
        apply_check_success: bool,
        apply_check_error: str,
        apply_success: bool,
        apply_error: str,
        pytest_exit_code: int | None,
        pytest_output: str,
        success: bool,
        started_at: float,
        mode: str = "patch",
        replacement_raw_output: str | None = None,
        replacement_edits: list[dict] | None = None,
        replacement_success: bool | None = None,
        replacement_error: str | None = None,
        model_output_type: str = "patch",
        patch_command: str = "",
        context: dict | None = None,
        test_summary_before: dict | None = None,
        model_call: dict | None = None,
    ) -> IterationRecord:
        test_summary_after_obj = parse_pytest_summary(pytest_output) if pytest_output else None
        test_summary_after = pytest_summary_to_dict(test_summary_after_obj)
        before_obj = None
        if test_summary_before is not None:
            before_obj = parse_pytest_summary("")
            before_obj.total = test_summary_before.get("total")
            before_obj.passed = int(test_summary_before.get("passed") or 0)
            before_obj.failed = int(test_summary_before.get("failed") or 0)
            before_obj.skipped = int(test_summary_before.get("skipped") or 0)
            before_obj.failed_tests = list(test_summary_before.get("failed_tests") or [])
        delta = failure_delta(before_obj, test_summary_after_obj)
        generated_diff = cleaned_patch if apply_success and patch_command == "git diff --" else ""
        parse_error = None
        if mode == "replacement" and replacement_success is False and not replacement_edits:
            parse_error = replacement_error
        apply_error_text = apply_error or (
            replacement_error if replacement_success is False and replacement_edits else ""
        )
        model_output = build_model_output(
            mode=mode,
            raw=raw_model_output,
            parsed_edits=replacement_edits,
            parse_error=parse_error,
            cleaned_patch=cleaned_patch,
        )
        apply_info = build_apply(
            method=mode,
            success=apply_success,
            error=apply_error_text or "",
            generated_diff=generated_diff,
            check_success=apply_check_success,
            check_error=apply_check_error,
            command=patch_command,
        )
        edits = edit_summary(
            mode=mode,
            replacement_edits=replacement_edits,
            diff_text=generated_diff or cleaned_patch,
        )
        result = iteration_result(
            success=success,
            mode=mode,
            raw_model_output=raw_model_output,
            model_parse_error=parse_error,
            apply_success=apply_success,
            apply_error=apply_error_text or "",
            apply_check_success=apply_check_success,
            apply_check_error=apply_check_error,
            pytest_exit_code=pytest_exit_code,
            delta=delta,
        )
        return IterationRecord(
            iteration=iteration,
            prompt=prompt,
            raw_model_output=raw_model_output,
            cleaned_patch=cleaned_patch,
            patch_path=str(patch_path),
            apply_check_success=apply_check_success,
            apply_check_error=apply_check_error,
            apply_success=apply_success,
            apply_error=apply_error,
            pytest_exit_code=pytest_exit_code,
            pytest_output=pytest_output,
            success=success,
            duration_seconds=time.perf_counter() - started_at,
            mode=mode,
            model_output_type=model_output_type,
            replacement_raw_output=replacement_raw_output,
            replacement_edits=replacement_edits,
            replacement_success=replacement_success,
            replacement_error=replacement_error,
            patch_command=patch_command,
            context=context,
            test_summary_before=test_summary_before,
            test_summary_after=test_summary_after,
            failure_delta=delta,
            iteration_result=result,
            generated_diff=generated_diff,
            model_output=model_output,
            apply=apply_info,
            edit_summary=edits,
            model_call=model_call,
        )
