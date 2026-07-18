from __future__ import annotations

from dataclasses import asdict
import time

from pyfixagent.agent.prompts import SYSTEM_PROMPT
from pyfixagent.agent.state import AgentState
from pyfixagent.context.pytest_summary import parse_pytest_summary, pytest_summary_to_dict
from pyfixagent.context.provider import ContextProvider
from pyfixagent.context.policy import ContextExpansionPolicy
from pyfixagent.core.contracts import EditProposal, RepairRequest
from pyfixagent.execution.test_runner import TestRunner
from pyfixagent.execution.workspace_session import WorkspaceSession
from pyfixagent.repair.backends.base import EditBackend
from pyfixagent.repair.evaluator import AttemptEvaluator
from pyfixagent.repair.model_client import ModelClient, ModelGenerationError
from pyfixagent.repair.prompting import PromptBuilder
from pyfixagent.repair.retry_policy import RetryPolicy
from pyfixagent.review.context import ReviewContextProvider
from pyfixagent.review.contracts import ReviewDecision, ReviewRequest
from pyfixagent.review.feedback import build_review_feedback
from pyfixagent.review.policy import ReviewPolicy
from pyfixagent.review.reviewer import SemanticReviewer
from pyfixagent.schemas import AgentResult, ReviewRecord
from pyfixagent.trace import collect_environment, final_summary


class RepairEngine:
    """Deterministic repair state machine composed from focused components."""

    def __init__(
        self,
        *,
        workspace_session: WorkspaceSession,
        test_runner: TestRunner,
        context_provider: ContextProvider,
        context_policy: ContextExpansionPolicy,
        prompt_builder: PromptBuilder,
        model_client: ModelClient,
        backends: dict[str, EditBackend],
        evaluator: AttemptEvaluator,
        retry_policy: RetryPolicy,
        semantic_review_enabled: bool,
        review_context_provider: ReviewContextProvider,
        semantic_reviewer: SemanticReviewer,
        review_policy: ReviewPolicy,
        review_max_feedback_chars: int,
    ):
        self.workspace_session = workspace_session
        self.test_runner = test_runner
        self.context_provider = context_provider
        self.context_policy = context_policy
        self.prompt_builder = prompt_builder
        self.model_client = model_client
        self.backends = backends
        self.evaluator = evaluator
        self.retry_policy = retry_policy
        self.semantic_review_enabled = semantic_review_enabled
        self.review_context_provider = review_context_provider
        self.semantic_reviewer = semantic_reviewer
        self.review_policy = review_policy
        self.review_max_feedback_chars = review_max_feedback_chars

    def run(self, request: RepairRequest) -> AgentResult:
        state = AgentState(
            task=request.task,
            workspace=request.workspace,
            original_workspace=request.workspace,
        )
        patch_applied = False
        try:
            prepared = self.workspace_session.prepare()
            state.workspace_state = prepared.state
            state.workspace_strategy = prepared.strategy
            if prepared.error:
                state.error = prepared.error
                return self._to_result(state, patch_applied)
            state.workspace = prepared.workspace
            state.file_tree = prepared.file_tree

            print("[agent] scanning workspace files...")
            print("[agent] running pytest before fix...")
            before = self.test_runner.run(state.workspace)
            state.test_output_before = before.output
            if before.infrastructure_error:
                state.error = "test execution infrastructure error; model was not called"
                return self._to_result(state, patch_applied)
            if before.success:
                print("[agent] tests already pass; no patch needed.")
                state.success = True
                state.visible_success = True
                state.acceptance_status = "not_run"
                return self._to_result(state, patch_applied)

            feedback = "No previous attempt."
            current_test_output = state.test_output_before
            active_review_feedback = ""
            active_review_ids: tuple[str, ...] = ()
            trigger = "pytest_failure"
            review_index = 0
            for iteration in range(1, request.max_iterations + 1):
                started_at = time.perf_counter()
                patch_path = self.workspace_session.patch_path(iteration)
                mode = self.retry_policy.mode
                print(f"[agent] iteration {iteration}/{request.max_iterations}: selecting context...")
                context_plan = self.context_policy.plan(
                    strategy=self.context_provider.strategy,
                    line_window=self.context_provider.line_window,
                    max_files=self.context_provider.max_files,
                    allow_full=self.context_provider.fallback_to_full,
                )
                context = self.context_provider.build(
                    state.workspace,
                    current_test_output,
                    plan=context_plan,
                )
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
                    record = self.evaluator.model_error_record(
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
                    record.context_expansion_level = context_plan.level
                    decision = self.retry_policy.after_model_error()
                    record.retry_reason = decision.reason
                    record.trigger = trigger
                    record.review_feedback_ids = list(active_review_ids)
                    state.iterations.append(record)
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
                    record = self.evaluator.apply_record(
                        iteration=iteration,
                        proposal=proposal,
                        result=backend_result,
                        started_at=started_at,
                        context=context.metadata,
                        test_summary_before=summary_before,
                    )
                    if backend_result.applied_to_workspace and state.workspace_strategy == "temporary_git_worktree":
                        self.workspace_session.rollback()
                        record.workspace_action = "rolled_back_after_apply_failure"
                    decision = self.retry_policy.after_apply(backend_result)
                    record.context_expansion_level = context_plan.level
                    record.retry_reason = decision.reason
                    record.trigger = trigger
                    record.review_feedback_ids = list(active_review_ids)
                    state.iterations.append(record)
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
                after = self.test_runner.run(state.workspace)
                state.test_output_after = after.output
                state.success = after.success
                state.error = None if state.success else f"tests still failed after applying {mode}"
                record = self.evaluator.apply_record(
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
                if after.infrastructure_error:
                    state.success = False
                    state.error = "test execution infrastructure error after applying repair"
                    record.iteration_result = {
                        "status": "execution_error",
                        "failure_type": "execution_error",
                        "reason": state.error,
                    }
                    if state.workspace_strategy == "temporary_git_worktree":
                        self.workspace_session.rollback()
                        record.workspace_action = "rolled_back_execution_error"
                    else:
                        record.workspace_action = "kept_in_place"
                    record.context_expansion_level = context_plan.level
                    record.trigger = trigger
                    record.review_feedback_ids = list(active_review_ids)
                    state.iterations.append(record)
                    return self._to_result(state, patch_applied)
                if state.success:
                    state.visible_success = True
                    checkpoint = self.workspace_session.checkpoint(iteration, kind="visible_candidate")
                    record.context_expansion_level = context_plan.level
                    record.trigger = trigger
                    record.review_feedback_ids = list(active_review_ids)
                    record.candidate_checkpoint = checkpoint
                    record.workspace_action = (
                        (
                            "checkpointed_visible_candidate"
                            if self.semantic_review_enabled
                            else "checkpointed_success"
                        )
                        if state.workspace_strategy == "temporary_git_worktree"
                        else "kept_in_place"
                    )
                    state.iterations.append(record)
                    if not self.semantic_review_enabled:
                        state.acceptance_status = "disabled"
                        return self._to_result(state, patch_applied)

                    review_index += 1
                    candidate_diff = self.workspace_session.candidate_diff()
                    review_context = self.review_context_provider.build(state.workspace, candidate_diff)
                    print(f"[agent] semantic review {review_index}: reviewing visible-pass candidate...")
                    execution = self.semantic_reviewer.review(
                        ReviewRequest(
                            task=request.task,
                            candidate_diff=candidate_diff,
                            visible_test_output=after.output,
                            context=review_context,
                            review_index=review_index,
                        ),
                        state.workspace,
                    )
                    error = execution.model_error or execution.parse_error
                    structural_cues = tuple(
                        cue for cue in review_context.metadata.get("structural_risk_cues", [])
                        if cue.get("id")
                    )
                    review_decision = self.review_policy.decide(
                        execution.outcome,
                        state.semantic_revisions_used,
                        error=error,
                        structural_cue_categories=tuple(
                            str(cue.get("category"))
                            for cue in structural_cues
                            if cue.get("category")
                        ),
                        structural_cue_ids=tuple(str(cue["id"]) for cue in structural_cues),
                    )
                    if review_decision.action == "revise" and iteration >= request.max_iterations:
                        review_decision = ReviewDecision(
                            "needs_review",
                            "edit iteration budget exhausted",
                            review_decision.blocking_risk_ids,
                        )
                    state.reviews.append(
                        ReviewRecord(
                            review_index=review_index,
                            based_on_iteration=iteration,
                            prompt=execution.prompt,
                            raw_model_output=execution.raw_output,
                            parsed_outcome=(
                                asdict(execution.outcome) if execution.outcome is not None else None
                            ),
                            parse_error=execution.parse_error,
                            model_error=execution.model_error,
                            model_calls=execution.model_calls,
                            context=execution.context,
                            policy_action=review_decision.action,
                            policy_reason=review_decision.reason,
                            blocking_risk_ids=list(review_decision.blocking_risk_ids),
                            candidate_checkpoint=checkpoint,
                        )
                    )
                    if review_decision.action in {"accept", "accept_with_warnings"}:
                        state.acceptance_status = (
                            "accepted_with_warnings"
                            if review_decision.action == "accept_with_warnings"
                            else "accepted"
                        )
                        state.success = True
                        state.error = None
                        return self._to_result(state, patch_applied)
                    if review_decision.action == "revise" and execution.outcome is not None:
                        active_review_feedback, active_review_ids = build_review_feedback(
                            execution.outcome,
                            self.review_max_feedback_chars,
                            review_decision.blocking_risk_ids,
                            structural_cues,
                        )
                        feedback = active_review_feedback
                        current_test_output = after.output
                        trigger = "semantic_revision"
                        state.semantic_revisions_used += 1
                        state.success = False
                        state.acceptance_status = "revising"
                        print(
                            f"[agent] semantic review {review_index}: blocking risks found; "
                            "requesting one bounded revision."
                        )
                        continue
                    state.success = False
                    state.acceptance_status = (
                        "review_error" if error else "abstained"
                        if execution.outcome and execution.outcome.verdict == "abstain"
                        else "rejected"
                    )
                    state.error = None
                    return self._to_result(state, patch_applied)

                failure_type = str((record.iteration_result or {}).get("failure_type") or "unknown")
                decision = self.retry_policy.after_test_failure(record.iteration_result)
                rolled_back = decision.rollback and state.workspace_strategy == "temporary_git_worktree"
                if rolled_back:
                    self.workspace_session.rollback()
                    record.workspace_action = f"rolled_back_{failure_type}"
                else:
                    self.workspace_session.checkpoint(iteration)
                    record.workspace_action = (
                        "checkpointed_partial"
                        if state.workspace_strategy == "temporary_git_worktree"
                        else "kept_in_place"
                    )
                    current_test_output = after.output
                if decision.expand_context:
                    self.context_policy.expand(decision.reason)
                record.context_expansion_level = context_plan.level
                record.retry_reason = decision.reason
                record.trigger = trigger
                record.review_feedback_ids = list(active_review_ids)
                state.iterations.append(record)
                test_feedback = self.prompt_builder.semantic_test_failure(
                    mode=mode,
                    failure_type=failure_type,
                    delta=record.failure_delta or {},
                    test_output=after.output,
                    rolled_back=rolled_back,
                    context_expansion_level=self.context_policy.level,
                )
                feedback = (
                    f"{active_review_feedback}\n\n{test_feedback}"
                    if active_review_feedback
                    else test_feedback
                )
                print(
                    f"[agent] iteration {iteration}/{request.max_iterations}: "
                    "tests still failed; retrying if possible."
                )

            if state.visible_success and self.semantic_review_enabled:
                state.success = False
                state.acceptance_status = "rejected"
                state.error = None
                return self._to_result(state, patch_applied)
            if state.error is None:
                state.error = "agent did not produce a successful patch"
            state.error = f"{state.error}; reached max_iterations={request.max_iterations}"
            return self._to_result(state, patch_applied)
        except Exception as exc:
            state.error = str(exc)
            state.success = False
            return self._to_result(state, patch_applied)
        finally:
            try:
                self.workspace_session.close()
            except Exception as exc:
                print(f"[agent] warning: temporary workspace cleanup failed: {exc}")

    def _to_result(self, state: AgentState, patch_applied: bool) -> AgentResult:
        if self.workspace_session.transaction.active is not None:
            final_patch, final_patch_path = self.workspace_session.export_final_patch()
            if state.workspace_strategy == "temporary_git_worktree":
                state.patch = final_patch
            if final_patch_path is not None:
                state.final_patch_path = str(final_patch_path)
            if state.visible_success:
                state.candidate_patch = final_patch
                state.candidate_patch_path = str(final_patch_path or "")
        result = AgentResult(
            task=state.task,
            workspace=str(state.original_workspace or state.workspace),
            success=state.success,
            patch_applied=patch_applied,
            test_output_before=state.test_output_before,
            test_output_after=state.test_output_after,
            patch=state.patch,
            iterations=state.iterations,
            workspace_strategy=state.workspace_strategy,
            final_patch_command=self._final_patch_command(state, patch_applied),
            error=state.error,
            environment=collect_environment(
                state.workspace,
                execution=self.test_runner.environment_metadata(),
            ),
            workspace_state=state.workspace_state,
            final_patch_path=state.final_patch_path,
            visible_success=state.visible_success,
            acceptance_status=state.acceptance_status,
            candidate_patch=state.candidate_patch,
            candidate_patch_path=state.candidate_patch_path,
            reviews=state.reviews,
            semantic_revisions_used=state.semantic_revisions_used,
        )
        result.final_summary = final_summary(result)
        return result

    @staticmethod
    def _final_patch_command(state: AgentState, patch_applied: bool) -> str:
        if state.workspace_strategy == "temporary_git_worktree" and state.final_patch_path:
            return (
                f'pyfixagent-apply --workspace "{state.original_workspace}" '
                f'--patch "{state.final_patch_path}"'
            )
        if patch_applied and state.patch:
            return "git diff --"
        if state.patch:
            return "git apply --check -"
        return ""
