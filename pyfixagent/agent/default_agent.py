from dataclasses import asdict
from datetime import datetime
from pathlib import Path
import time

from pyfixagent.agent.prompts import PATCH_PROMPT, REPLACEMENT_PROMPT, SYSTEM_PROMPT
from pyfixagent.agent.state import AgentState
from pyfixagent.context.builder import context_trace_metadata, render_selected_context
from pyfixagent.context.pytest_summary import parse_pytest_summary, pytest_summary_to_dict
from pyfixagent.context.selector import select_context
from pyfixagent.context.traceback_parser import parse_pytest_failure_output
from pyfixagent.models.base import BaseModel
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.schemas import AgentResult, IterationRecord
from pyfixagent.tools.file_tools import list_files, read_python_files
from pyfixagent.tools.patch_tools import apply_patch, check_patch, clean_patch_text, get_git_diff, save_patch
from pyfixagent.tools.replacement_tools import apply_replacements, parse_replacements
from pyfixagent.tools.shell_tools import run_pytest
from pyfixagent.trace import (
    build_apply,
    build_model_output,
    collect_environment,
    edit_summary,
    failure_delta,
    final_summary,
    iteration_result,
    model_call_metadata,
)


class DefaultAgent:
    def __init__(
        self,
        model: BaseModel,
        sandbox: LocalSandbox,
        patch_output_dir: Path,
        max_iterations: int = 1,
        initial_mode: str = "replacement",
        context_strategy: str = "traceback",
        context_line_window: int = 40,
        context_max_files: int = 6,
        context_fallback_to_full: bool = True,
        context_include_tests: bool = True,
    ):
        self.model = model
        self.sandbox = sandbox
        self.patch_output_dir = Path(patch_output_dir)
        self.max_iterations = max(1, max_iterations)
        if initial_mode not in {"patch", "replacement"}:
            raise ValueError("initial_mode must be 'patch' or 'replacement'")
        self.initial_mode = initial_mode
        if context_strategy not in {"full", "traceback"}:
            raise ValueError("context_strategy must be 'full' or 'traceback'")
        self.context_strategy = context_strategy
        self.context_line_window = max(0, context_line_window)
        self.context_max_files = max(1, context_max_files)
        self.context_fallback_to_full = context_fallback_to_full
        self.context_include_tests = context_include_tests

    def run(self, task: str) -> AgentResult:
        state = AgentState(task=task, workspace=self.sandbox.workspace)
        patch_applied = False

        try:
            print("[agent] scanning workspace files...")
            state.file_tree = list_files(state.workspace)

            print("[agent] running pytest before fix...")
            before = run_pytest(self.sandbox)
            state.test_output_before = self._format_test_output(before)
            if before.exit_code == 0:
                print("[agent] tests already pass; no patch needed.")
                state.success = True
                return self._to_result(state, patch_applied)

            feedback = "No previous attempt."
            consecutive_patch_check_failures = 0
            replacement_mode_active = self.initial_mode == "replacement"
            current_test_output = state.test_output_before
            for iteration in range(1, self.max_iterations + 1):
                iteration_start = time.perf_counter()
                patch_path = self.patch_output_dir / (
                    f"patch_{datetime.now().strftime('%Y%m%d_%H%M%S')}_attempt_{iteration}.patch"
                )
                print(f"[agent] iteration {iteration}/{self.max_iterations}: selecting context...")
                python_files, context_metadata = self._build_context_prompt(
                    workspace=state.workspace,
                    pytest_output=current_test_output,
                )
                test_summary_before = parse_pytest_summary(current_test_output)
                mode = "replacement" if replacement_mode_active else "patch"
                initial_test_output = (
                    state.test_output_before
                    if iteration == 1
                    else "Omitted after iteration 1. Use Current pytest output as the source of truth."
                )

                def build_record(**kwargs) -> IterationRecord:
                    return self._build_iteration_record(
                        context=context_metadata,
                        test_summary_before=pytest_summary_to_dict(test_summary_before),
                        **kwargs,
                    )

                if mode == "replacement":
                    prompt = REPLACEMENT_PROMPT.format(
                        task=task,
                        iteration=iteration,
                        max_iterations=self.max_iterations,
                        file_tree=state.file_tree,
                        initial_test_output=initial_test_output,
                        current_test_output=current_test_output,
                        feedback=feedback,
                        python_files=python_files,
                    )
                    context_metadata["prompt_chars"] = len(prompt)
                    self._update_context_prompt_chars(context_metadata, len(prompt))

                    print(
                        f"[agent] iteration {iteration}/{self.max_iterations}: "
                        "generating replacement JSON with model..."
                    )
                    raw_replacement = ""
                    replacement_edits = None
                    model_call = model_call_metadata(self.model)
                    try:
                        model_start = time.perf_counter()
                        raw_replacement = self.model.generate_patch(SYSTEM_PROMPT, prompt)
                        model_call = model_call_metadata(self.model, time.perf_counter() - model_start)
                        edits = parse_replacements(raw_replacement)
                        replacement_edits = self._replacement_edits_to_dicts(edits)
                        replacement_result = apply_replacements(state.workspace, edits)
                    except Exception as exc:
                        if model_call.get("duration_seconds") is None:
                            model_call = model_call_metadata(self.model, time.perf_counter() - model_start)
                        state.error = str(exc)
                        state.iterations.append(
                            build_record(
                                iteration=iteration,
                                prompt=prompt,
                                raw_model_output=raw_replacement,
                                cleaned_patch="",
                                patch_path="",
                                apply_check_success=False,
                                apply_check_error="",
                                apply_success=False,
                                apply_error="",
                                pytest_exit_code=None,
                                pytest_output="",
                                success=False,
                                started_at=iteration_start,
                                mode="replacement",
                                model_output_type="replacement",
                                replacement_raw_output=raw_replacement,
                                replacement_edits=replacement_edits,
                                replacement_success=False,
                                replacement_error=state.error,
                                patch_command="",
                                model_call=model_call,
                            )
                        )
                        feedback = self._replacement_failure_feedback(raw_replacement, state.error)
                        print(
                            f"[agent] iteration {iteration}/{self.max_iterations}: "
                            "replacement parsing failed; retrying if possible."
                        )
                        continue

                    if not replacement_result.success:
                        state.error = replacement_result.error
                        state.iterations.append(
                            build_record(
                                iteration=iteration,
                                prompt=prompt,
                                raw_model_output=raw_replacement,
                                cleaned_patch="",
                                patch_path="",
                                apply_check_success=False,
                                apply_check_error="",
                                apply_success=False,
                                apply_error="",
                                pytest_exit_code=None,
                                pytest_output="",
                                success=False,
                                started_at=iteration_start,
                                mode="replacement",
                                model_output_type="replacement",
                                replacement_raw_output=raw_replacement,
                                replacement_edits=replacement_edits,
                                replacement_success=False,
                                replacement_error=replacement_result.error,
                                patch_command="",
                                model_call=model_call,
                            )
                        )
                        feedback = self._replacement_failure_feedback(raw_replacement, replacement_result.error or "")
                        print(
                            f"[agent] iteration {iteration}/{self.max_iterations}: "
                            "replacement apply failed; retrying if possible."
                        )
                        continue

                    patch_applied = True
                    diff_result = get_git_diff(state.workspace)
                    if not diff_result.success:
                        state.error = diff_result.error
                        state.iterations.append(
                            build_record(
                                iteration=iteration,
                                prompt=prompt,
                                raw_model_output=raw_replacement,
                                cleaned_patch="",
                                patch_path="",
                                apply_check_success=False,
                                apply_check_error="",
                                apply_success=True,
                                apply_error=diff_result.error or "",
                                pytest_exit_code=None,
                                pytest_output="",
                                success=False,
                                started_at=iteration_start,
                                mode="replacement",
                                model_output_type="replacement",
                                replacement_raw_output=raw_replacement,
                                replacement_edits=replacement_edits,
                                replacement_success=True,
                                replacement_error=None,
                                patch_command="git diff --",
                                model_call=model_call,
                            )
                        )
                        feedback = self._replacement_failure_feedback(raw_replacement, diff_result.error or "")
                        print(
                            f"[agent] iteration {iteration}/{self.max_iterations}: "
                            "replacement applied but git diff failed; retrying if possible."
                        )
                        continue

                    state.patch = diff_result.stdout
                    save_patch(state.workspace, state.patch, patch_path)
                    print(f"[agent] iteration {iteration}/{self.max_iterations}: running pytest after replacement...")
                    after = run_pytest(self.sandbox)
                    state.test_output_after = self._format_test_output(after)
                    state.success = after.exit_code == 0
                    if state.success:
                        state.error = None
                        state.iterations.append(
                            build_record(
                                iteration=iteration,
                                prompt=prompt,
                                raw_model_output=raw_replacement,
                                cleaned_patch=state.patch,
                                patch_path=patch_path,
                                apply_check_success=False,
                                apply_check_error="",
                                apply_success=True,
                                apply_error="",
                                pytest_exit_code=after.exit_code,
                                pytest_output=state.test_output_after,
                                success=True,
                                started_at=iteration_start,
                                mode="replacement",
                                model_output_type="replacement",
                                replacement_raw_output=raw_replacement,
                                replacement_edits=replacement_edits,
                                replacement_success=True,
                                replacement_error=None,
                                patch_command="git diff --",
                                model_call=model_call,
                            )
                        )
                        return self._to_result(state, patch_applied)

                    state.error = "tests still failed after applying replacement"
                    state.iterations.append(
                        build_record(
                            iteration=iteration,
                            prompt=prompt,
                            raw_model_output=raw_replacement,
                            cleaned_patch=state.patch,
                            patch_path=patch_path,
                            apply_check_success=False,
                            apply_check_error="",
                            apply_success=True,
                            apply_error="",
                            pytest_exit_code=after.exit_code,
                            pytest_output=state.test_output_after,
                            success=False,
                            started_at=iteration_start,
                            mode="replacement",
                            model_output_type="replacement",
                            replacement_raw_output=raw_replacement,
                            replacement_edits=replacement_edits,
                            replacement_success=True,
                            replacement_error=None,
                            patch_command="git diff --",
                            model_call=model_call,
                        )
                    )
                    current_test_output = state.test_output_after
                    feedback = self._replacement_test_failure_feedback(state.test_output_after)
                    print(
                        f"[agent] iteration {iteration}/{self.max_iterations}: "
                        "tests still failed after replacement; retrying if possible."
                    )
                    continue

                prompt = PATCH_PROMPT.format(
                    task=task,
                    iteration=iteration,
                    max_iterations=self.max_iterations,
                    file_tree=state.file_tree,
                    initial_test_output=initial_test_output,
                    current_test_output=current_test_output,
                    feedback=feedback,
                    python_files=python_files,
                )
                context_metadata["prompt_chars"] = len(prompt)
                self._update_context_prompt_chars(context_metadata, len(prompt))

                print(f"[agent] iteration {iteration}/{self.max_iterations}: generating patch with model...")
                model_call = model_call_metadata(self.model)
                try:
                    model_start = time.perf_counter()
                    raw_patch = self.model.generate_patch(SYSTEM_PROMPT, prompt)
                    model_call = model_call_metadata(self.model, time.perf_counter() - model_start)
                except Exception as exc:
                    model_call = model_call_metadata(self.model, time.perf_counter() - model_start)
                    state.error = str(exc)
                    state.iterations.append(
                        build_record(
                            iteration=iteration,
                            prompt=prompt,
                            raw_model_output="",
                            cleaned_patch="",
                            patch_path=patch_path,
                            apply_check_success=False,
                            apply_check_error="",
                            apply_success=False,
                            apply_error=state.error,
                            pytest_exit_code=None,
                            pytest_output="",
                            success=False,
                            started_at=iteration_start,
                            patch_command="",
                            model_call=model_call,
                        )
                    )
                    return self._to_result(state, patch_applied)

                state.patch = clean_patch_text(raw_patch)

                print(f"[agent] iteration {iteration}/{self.max_iterations}: saving patch to {patch_path}...")
                save_patch(state.workspace, state.patch, patch_path)

                print(f"[agent] iteration {iteration}/{self.max_iterations}: checking patch with git apply --check...")
                check_result = check_patch(state.workspace, state.patch)
                if not check_result.success:
                    consecutive_patch_check_failures += 1
                    if consecutive_patch_check_failures >= 2:
                        replacement_mode_active = True
                    state.error = check_result.error
                    state.iterations.append(
                        build_record(
                            iteration=iteration,
                            prompt=prompt,
                            raw_model_output=raw_patch,
                            cleaned_patch=state.patch,
                            patch_path=patch_path,
                            apply_check_success=False,
                            apply_check_error=check_result.error or check_result.stderr,
                            apply_success=False,
                            apply_error="",
                            pytest_exit_code=None,
                            pytest_output="",
                            success=False,
                            started_at=iteration_start,
                            patch_command="git apply --check -",
                            model_call=model_call,
                        )
                    )
                    feedback = self._patch_failure_feedback(state.patch, check_result.error or check_result.stderr)
                    print(f"[agent] iteration {iteration}/{self.max_iterations}: patch check failed; retrying if possible.")
                    continue

                print(f"[agent] iteration {iteration}/{self.max_iterations}: applying patch with git apply...")
                patch_result = apply_patch(state.workspace, state.patch)
                if not patch_result.success:
                    state.error = patch_result.error
                    state.iterations.append(
                        build_record(
                            iteration=iteration,
                            prompt=prompt,
                            raw_model_output=raw_patch,
                            cleaned_patch=state.patch,
                            patch_path=patch_path,
                            apply_check_success=True,
                            apply_check_error="",
                            apply_success=False,
                            apply_error=patch_result.error or patch_result.stderr,
                            pytest_exit_code=None,
                            pytest_output="",
                            success=False,
                            started_at=iteration_start,
                            patch_command="git apply -",
                            model_call=model_call,
                        )
                    )
                    feedback = self._patch_failure_feedback(state.patch, patch_result.error or "")
                    print(f"[agent] iteration {iteration}/{self.max_iterations}: patch failed; retrying if possible.")
                    continue

                patch_applied = True
                consecutive_patch_check_failures = 0
                diff_result = get_git_diff(state.workspace)
                if not diff_result.success:
                    state.error = diff_result.error
                    state.iterations.append(
                        build_record(
                            iteration=iteration,
                            prompt=prompt,
                            raw_model_output=raw_patch,
                            cleaned_patch=state.patch,
                            patch_path=patch_path,
                            apply_check_success=True,
                            apply_check_error="",
                            apply_success=True,
                            apply_error=diff_result.error or "",
                            pytest_exit_code=None,
                            pytest_output="",
                            success=False,
                            started_at=iteration_start,
                            patch_command="git diff --",
                            model_call=model_call,
                        )
                    )
                    feedback = self._patch_failure_feedback(state.patch, diff_result.error or "")
                    print(
                        f"[agent] iteration {iteration}/{self.max_iterations}: "
                        "patch applied but git diff failed; retrying if possible."
                    )
                    continue

                state.patch = diff_result.stdout
                save_patch(state.workspace, state.patch, patch_path)
                print(f"[agent] iteration {iteration}/{self.max_iterations}: running pytest after fix...")
                after = run_pytest(self.sandbox)
                state.test_output_after = self._format_test_output(after)
                state.success = after.exit_code == 0
                if state.success:
                    state.error = None
                    state.iterations.append(
                        build_record(
                            iteration=iteration,
                            prompt=prompt,
                            raw_model_output=raw_patch,
                            cleaned_patch=state.patch,
                            patch_path=patch_path,
                            apply_check_success=True,
                            apply_check_error="",
                            apply_success=True,
                            apply_error="",
                            pytest_exit_code=after.exit_code,
                            pytest_output=state.test_output_after,
                            success=True,
                            started_at=iteration_start,
                            patch_command="git diff --",
                            model_call=model_call,
                        )
                    )
                    return self._to_result(state, patch_applied)

                state.error = "tests still failed after applying patch"
                state.iterations.append(
                    build_record(
                        iteration=iteration,
                        prompt=prompt,
                        raw_model_output=raw_patch,
                        cleaned_patch=state.patch,
                        patch_path=patch_path,
                        apply_check_success=True,
                        apply_check_error="",
                        apply_success=True,
                        apply_error="",
                        pytest_exit_code=after.exit_code,
                        pytest_output=state.test_output_after,
                        success=False,
                        started_at=iteration_start,
                        patch_command="git diff --",
                        model_call=model_call,
                    )
                )
                current_test_output = state.test_output_after
                feedback = self._test_failure_feedback(state.test_output_after)
                print(f"[agent] iteration {iteration}/{self.max_iterations}: tests still failed; retrying if possible.")

            if state.error is None:
                state.error = "agent did not produce a successful patch"
            state.error = f"{state.error}; reached max_iterations={self.max_iterations}"
            return self._to_result(state, patch_applied)
        except Exception as exc:
            state.error = str(exc)
            return self._to_result(state, patch_applied)

    @staticmethod
    def _format_test_output(result) -> str:
        parts = [
            f"command: {' '.join(result.command)}",
            f"exit_code: {result.exit_code}",
            f"duration: {result.duration:.2f}s",
            f"timeout: {result.timeout}",
            "stdout:",
            result.stdout,
            "stderr:",
            result.stderr,
        ]
        return "\n".join(parts)

    def _build_context_prompt(self, workspace: Path, pytest_output: str) -> tuple[str, dict]:
        summary = parse_pytest_failure_output(pytest_output)
        selected_context = select_context(
            summary=summary,
            workspace=workspace,
            strategy=self.context_strategy,
            line_window=self.context_line_window,
            max_files=self.context_max_files,
            fallback_to_full_context=self.context_fallback_to_full,
            include_tests=self.context_include_tests,
        )

        if self.context_strategy == "full":
            python_files = read_python_files(workspace)
        else:
            python_files = render_selected_context(selected_context)

        selected_context.prompt_chars = len(python_files)
        metadata = context_trace_metadata(selected_context)
        metadata["pytest_output_chars"] = len(pytest_output)
        metadata["stats"]["pytest_output_chars"] = len(pytest_output)
        metadata["failed_tests"] = summary.failed_tests
        metadata["exception_type"] = summary.exception_type
        metadata["error_message"] = summary.error_message
        metadata["raw_traceback_frames"] = [
            {
                "path": frame.path,
                "line": frame.line,
                "function": frame.function,
            }
            for frame in summary.frames
        ]
        return python_files, metadata

    @staticmethod
    def _update_context_prompt_chars(context: dict, prompt_chars: int) -> None:
        context["prompt_chars"] = prompt_chars
        stats = context.setdefault("stats", {})
        stats["prompt_chars"] = prompt_chars

    @staticmethod
    def _patch_failure_feedback(patch: str, error: str) -> str:
        return (
            "The previous model response could not be applied by git apply.\n"
            "Return a valid unified diff patch only. Do not use SEARCH/REPLACE blocks.\n"
            f"git apply error:\n{error}\n\n"
            f"Previous invalid patch:\n{patch}"
        )

    @staticmethod
    def _test_failure_feedback(test_output_after: str) -> str:
        return (
            "The previous patch was applied, but pytest still failed.\n"
            "Generate a new incremental unified diff patch against the current Python files.\n"
            f"Pytest output after previous patch:\n{test_output_after}"
        )

    @staticmethod
    def _replacement_failure_feedback(raw_output: str, error: str) -> str:
        return (
            "The previous replacement response could not be parsed or applied.\n"
            "Use the failure reason below to fix the next JSON replacement attempt.\n"
            "If old text appears multiple times, either make old longer with surrounding context or include start_line.\n"
            "Return only a JSON array of objects with path, old, and new string fields.\n"
            "Do not return a unified diff patch or Markdown code block.\n"
            f"Replacement failure reason:\n{error}\n\n"
            f"Previous replacement response:\n{raw_output}"
        )

    @staticmethod
    def _replacement_test_failure_feedback(test_output_after: str) -> str:
        return (
            "The previous replacement was applied, but pytest still failed.\n"
            "Return a new JSON array of small, exact old/new replacements against the current Python files.\n"
            f"Pytest output after previous replacement:\n{test_output_after}"
        )

    @staticmethod
    def _build_iteration_record(
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
        apply_error_text = apply_error or (replacement_error if replacement_success is False and replacement_edits else "")
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

    @staticmethod
    def _to_result(state: AgentState, patch_applied: bool) -> AgentResult:
        result = AgentResult(
            task=state.task,
            workspace=str(state.workspace),
            success=state.success,
            patch_applied=patch_applied,
            test_output_before=state.test_output_before,
            test_output_after=state.test_output_after,
            patch=state.patch,
            iterations=state.iterations,
            workspace_strategy="incremental_repair",
            final_patch_command=DefaultAgent._final_patch_command(state, patch_applied),
            error=state.error,
            environment=collect_environment(state.workspace),
        )
        result.final_summary = final_summary(result)
        return result

    @staticmethod
    def _final_patch_command(state: AgentState, patch_applied: bool) -> str:
        if patch_applied and state.patch:
            return "git diff --"
        if state.patch:
            return "git apply --check -"
        return ""

    @staticmethod
    def _replacement_edits_to_dicts(edits) -> list[dict]:
        result: list[dict] = []
        for edit in edits:
            item = asdict(edit)
            if item.get("start_line") is None:
                item.pop("start_line", None)
            result.append(item)
        return result
