from __future__ import annotations

import time

from pyfixagent.agent.prompts import SYSTEM_PROMPT
from pyfixagent.agent.state import AgentState
from pyfixagent.context.pytest_summary import parse_pytest_summary, pytest_summary_to_dict
from pyfixagent.context.provider import ContextProvider
from pyfixagent.core.contracts import EditProposal, RepairRequest
from pyfixagent.execution.test_runner import TestRunner
from pyfixagent.execution.workspace_session import WorkspaceSession
from pyfixagent.repair.backends.base import EditBackend
from pyfixagent.repair.evaluator import AttemptEvaluator
from pyfixagent.repair.model_client import ModelClient, ModelGenerationError
from pyfixagent.repair.prompting import PromptBuilder
from pyfixagent.repair.retry_policy import RetryPolicy
from pyfixagent.schemas import AgentResult
from pyfixagent.trace import collect_environment, final_summary


class RepairEngine:
    """Deterministic repair state machine composed from focused components."""

    def __init__(
        self,
        *,
        workspace_session: WorkspaceSession,
        test_runner: TestRunner,
        context_provider: ContextProvider,
        prompt_builder: PromptBuilder,
        model_client: ModelClient,
        backends: dict[str, EditBackend],
        evaluator: AttemptEvaluator,
        retry_policy: RetryPolicy,
    ):
        self.workspace_session = workspace_session
        self.test_runner = test_runner
        self.context_provider = context_provider
        self.prompt_builder = prompt_builder
        self.model_client = model_client
        self.backends = backends
        self.evaluator = evaluator
        self.retry_policy = retry_policy

    def run(self, request: RepairRequest) -> AgentResult:
        state = AgentState(task=request.task, workspace=request.workspace)
        patch_applied = False
        try:
            prepared = self.workspace_session.prepare()
            state.workspace_state = prepared.state
            if prepared.error:
                state.error = prepared.error
                return self._to_result(state, patch_applied)
            state.file_tree = prepared.file_tree

            print("[agent] scanning workspace files...")
            print("[agent] running pytest before fix...")
            before = self.test_runner.run()
            state.test_output_before = before.output
            if before.success:
                print("[agent] tests already pass; no patch needed.")
                state.success = True
                return self._to_result(state, patch_applied)

            feedback = "No previous attempt."
            current_test_output = state.test_output_before
            for iteration in range(1, request.max_iterations + 1):
                started_at = time.perf_counter()
                patch_path = self.workspace_session.patch_path(iteration)
                mode = self.retry_policy.mode
                print(f"[agent] iteration {iteration}/{request.max_iterations}: selecting context...")
                context = self.context_provider.build(state.workspace, current_test_output)
                summary_before = pytest_summary_to_dict(parse_pytest_summary(current_test_output))
                initial_output = (
                    state.test_output_before
                    if iteration == 1
                    else "Omitted after iteration 1. Use Current pytest output as the source of truth."
                )
                prompt = self.prompt_builder.build(
                    mode=mode,
                    task=request.task,
                    iteration=iteration,
                    max_iterations=request.max_iterations,
                    file_tree=state.file_tree,
                    initial_test_output=initial_output,
                    current_test_output=current_test_output,
                    feedback=feedback,
                    context=context,
                )

                label = "replacement JSON" if mode == "replacement" else "patch"
                print(f"[agent] iteration {iteration}/{request.max_iterations}: generating {label} with model...")
                try:
                    raw_output, model_call = self.model_client.generate(SYSTEM_PROMPT, prompt)
                except ModelGenerationError as exc:
                    state.error = str(exc)
                    state.iterations.append(
                        self.evaluator.model_error_record(
                            iteration=iteration,
                            prompt=prompt,
                            patch_path=patch_path,
                            started_at=started_at,
                            mode=mode,
                            error=state.error,
                            context=context.metadata,
                            test_summary_before=summary_before,
                            model_call=exc.metadata,
                        )
                    )
                    decision = self.retry_policy.after_model_error()
                    if not decision.continue_repair:
                        return self._to_result(state, patch_applied)
                    feedback = self.prompt_builder.replacement_failure("", state.error)
                    print(
                        f"[agent] iteration {iteration}/{request.max_iterations}: "
                        "replacement generation failed; retrying if possible."
                    )
                    continue

                proposal = EditProposal(mode=mode, prompt=prompt, raw_output=raw_output, model_call=model_call)
                backend_result = self.backends[mode].apply(state.workspace, proposal.raw_output, patch_path)
                patch_applied = patch_applied or backend_result.applied_to_workspace
                if mode == "patch":
                    state.patch = backend_result.cleaned_patch
                elif backend_result.success:
                    state.patch = backend_result.cleaned_patch

                if not backend_result.success:
                    state.error = backend_result.error
                    state.iterations.append(
                        self.evaluator.apply_record(
                            iteration=iteration,
                            proposal=proposal,
                            result=backend_result,
                            started_at=started_at,
                            context=context.metadata,
                            test_summary_before=summary_before,
                        )
                    )
                    decision = self.retry_policy.after_apply(backend_result)
                    feedback = (
                        self.prompt_builder.mode_switch_failure(backend_result, decision.next_mode)
                        if decision.next_mode != mode
                        else self.prompt_builder.apply_failure(backend_result)
                    )
                    action = self.prompt_builder.failure_action(backend_result)
                    print(
                        f"[agent] iteration {iteration}/{request.max_iterations}: "
                        f"{action}; retrying if possible."
                    )
                    continue

                self.retry_policy.after_apply(backend_result)
                state.patch = backend_result.cleaned_patch
                operation = "replacement" if mode == "replacement" else "fix"
                print(
                    f"[agent] iteration {iteration}/{request.max_iterations}: "
                    f"running pytest after {operation}..."
                )
                after = self.test_runner.run()
                state.test_output_after = after.output
                state.success = after.success
                state.error = None if state.success else f"tests still failed after applying {mode}"
                state.iterations.append(
                    self.evaluator.apply_record(
                        iteration=iteration,
                        proposal=proposal,
                        result=backend_result,
                        started_at=started_at,
                        context=context.metadata,
                        test_summary_before=summary_before,
                        pytest_exit_code=after.exit_code,
                        pytest_output=after.output,
                        success=state.success,
                    )
                )
                if state.success:
                    return self._to_result(state, patch_applied)

                current_test_output = after.output
                self.retry_policy.after_test_failure()
                feedback = (
                    self.prompt_builder.replacement_test_failure(after.output)
                    if mode == "replacement"
                    else self.prompt_builder.patch_test_failure(after.output)
                )
                print(
                    f"[agent] iteration {iteration}/{request.max_iterations}: "
                    "tests still failed; retrying if possible."
                )

            if state.error is None:
                state.error = "agent did not produce a successful patch"
            state.error = f"{state.error}; reached max_iterations={request.max_iterations}"
            return self._to_result(state, patch_applied)
        except Exception as exc:
            state.error = str(exc)
            state.success = False
            return self._to_result(state, patch_applied)

    def _to_result(self, state: AgentState, patch_applied: bool) -> AgentResult:
        result = AgentResult(
            task=state.task,
            workspace=str(state.workspace),
            success=state.success,
            patch_applied=patch_applied,
            test_output_before=state.test_output_before,
            test_output_after=state.test_output_after,
            patch=state.patch,
            iterations=state.iterations,
            workspace_strategy=(
                "in_place_clean_guard" if self.workspace_session.require_clean else "incremental_repair"
            ),
            final_patch_command=self._final_patch_command(state, patch_applied),
            error=state.error,
            environment=collect_environment(state.workspace),
            workspace_state=state.workspace_state,
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
