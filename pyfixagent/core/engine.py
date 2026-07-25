from __future__ import annotations

from dataclasses import asdict, dataclass, field
import time

from pyfixagent.agent.prompts import SYSTEM_PROMPT
from pyfixagent.agent.state import AgentState
from pyfixagent.context.policy import ContextExpansionPolicy
from pyfixagent.context.provider import ContextProvider
from pyfixagent.context.pytest_summary import parse_pytest_summary, pytest_summary_to_dict
from pyfixagent.core.contracts import ContextBundle, EditProposal, RepairRequest
from pyfixagent.execution.test_runner import TestRunner
from pyfixagent.execution.workspace_session import WorkspaceSession
from pyfixagent.repair.backends.base import EditBackend
from pyfixagent.repair.evaluator import AttemptEvaluator
from pyfixagent.repair.model_client import ModelClient, ModelGenerationError
from pyfixagent.repair.prompting import PromptBuilder
from pyfixagent.repair.retry_policy import RetryPolicy
from pyfixagent.review.context import ReviewContextProvider
from pyfixagent.review.contracts import ReviewDecision, ReviewExecution, ReviewRequest
from pyfixagent.review.feedback import build_review_feedback
from pyfixagent.review.policy import ReviewPolicy
from pyfixagent.review.reviewer import SemanticReviewer
from pyfixagent.sandbox.base import CommandResult
from pyfixagent.schemas import AgentResult, IterationRecord, ReviewRecord
from pyfixagent.trace import collect_environment, final_summary
from pyfixagent.utils.logger import get_logger


logger = get_logger(__name__)


@dataclass(frozen=True)
class EngineServices:
    """The collaborating services required by one repair run."""

    workspace_session: WorkspaceSession
    test_runner: TestRunner
    context_provider: ContextProvider
    context_policy: ContextExpansionPolicy
    prompt_builder: PromptBuilder
    model_client: ModelClient
    backends: dict[str, EditBackend]
    evaluator: AttemptEvaluator
    retry_policy: RetryPolicy
    semantic_review_enabled: bool
    review_context_provider: ReviewContextProvider
    semantic_reviewer: SemanticReviewer
    review_policy: ReviewPolicy
    review_max_feedback_chars: int


@dataclass
class RepairRuntime:
    """Mutable control state for a single call to :meth:`RepairEngine.run`."""

    patch_applied: bool = False
    feedback: str = "No previous attempt."
    current_test_output: str = ""
    active_review_feedback: str = ""
    active_review_ids: tuple[str, ...] = ()
    trigger: str = "pytest_failure"
    review_index: int = 0
    finished: bool = False


@dataclass(frozen=True)
class IterationPlan:
    """Evidence and proposal produced before applying one repair attempt."""

    iteration: int
    started_at: float
    patch_path: object
    mode: str
    context_plan: object
    context: ContextBundle
    test_summary_before: dict
    proposal: EditProposal


class RepairEngine:
    """Deterministic repair state machine composed from focused components."""

    def __init__(self, services: EngineServices):
        self.services = services
        # Retain direct attributes for callers that inspect the assembled engine.
        self.workspace_session = services.workspace_session
        self.test_runner = services.test_runner
        self.context_provider = services.context_provider
        self.context_policy = services.context_policy
        self.prompt_builder = services.prompt_builder
        self.model_client = services.model_client
        self.backends = services.backends
        self.evaluator = services.evaluator
        self.retry_policy = services.retry_policy
        self.semantic_review_enabled = services.semantic_review_enabled
        self.review_context_provider = services.review_context_provider
        self.semantic_reviewer = services.semantic_reviewer
        self.review_policy = services.review_policy
        self.review_max_feedback_chars = services.review_max_feedback_chars

    def run(self, request: RepairRequest) -> AgentResult:
        state = AgentState(task=request.task, workspace=request.workspace, original_workspace=request.workspace)
        runtime = RepairRuntime()
        result: AgentResult | None = None
        try:
            runtime.finished = self._prepare(state, runtime)
            while not runtime.finished and len(state.iterations) < request.max_iterations:
                iteration = len(state.iterations) + 1
                runtime.finished = self._run_iteration(state, runtime, request, iteration)
            if not runtime.finished:
                self._mark_iteration_limit(state, request)
        except (OSError, RuntimeError, ValueError) as exc:
            state.error = str(exc)
            state.success = False
            logger.exception("repair run stopped by an expected runtime failure")
        finally:
            result = self._to_result(state, runtime.patch_applied)
            self._close_workspace()
        assert result is not None
        return result

    def _prepare(self, state: AgentState, runtime: RepairRuntime) -> bool:
        prepared = self.workspace_session.prepare()
        state.workspace_state = prepared.state
        state.workspace_strategy = prepared.strategy
        if prepared.error:
            state.error = prepared.error
            return True
        state.workspace = prepared.workspace
        state.file_tree = prepared.file_tree

        logger.info("scanning workspace files")
        logger.info("running pytest before fix")
        before = self.test_runner.run(state.workspace)
        state.test_output_before = before.output
        runtime.current_test_output = before.output
        if before.infrastructure_error:
            state.error = "test execution infrastructure error; model was not called"
            return True
        if before.success:
            logger.info("tests already pass; no patch needed")
            state.success = True
            state.visible_success = True
            state.acceptance_status = "not_run"
            return True
        return False

    def _run_iteration(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        request: RepairRequest,
        iteration: int,
    ) -> bool:
        plan = self._plan_and_generate(state, runtime, request, iteration)
        if plan is None:
            return runtime.finished

        backend_result = self._apply(state, runtime, plan)
        if not backend_result.success:
            self._handle_apply_failure(state, runtime, plan, backend_result)
            return False

        verified = self._verify(state, runtime, plan, backend_result)
        if verified is None:
            return True
        record, after = verified
        return self._accept_or_retry(state, runtime, request, plan, record, after)

    def _plan_and_generate(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        request: RepairRequest,
        iteration: int,
    ) -> IterationPlan | None:
        started_at = time.perf_counter()
        patch_path = self.workspace_session.patch_path(iteration)
        mode = self.retry_policy.mode
        logger.info("iteration %s/%s: selecting context", iteration, request.max_iterations)
        context_plan = self.context_policy.plan(
            strategy=self.context_provider.strategy,
            line_window=self.context_provider.line_window,
            max_files=self.context_provider.max_files,
            allow_full=self.context_provider.fallback_to_full,
        )
        context = self.context_provider.build(state.workspace, runtime.current_test_output, plan=context_plan)
        summary_before = pytest_summary_to_dict(parse_pytest_summary(runtime.current_test_output))
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
            current_test_output=runtime.current_test_output,
            feedback=runtime.feedback,
            context=context,
        )
        label = "replacement JSON" if mode == "replacement" else "patch"
        logger.info("iteration %s/%s: generating %s with model", iteration, request.max_iterations, label)
        try:
            raw_output, model_call = self.model_client.generate(SYSTEM_PROMPT, prompt)
        except ModelGenerationError as exc:
            self._handle_model_error(
                state,
                runtime,
                iteration=iteration,
                prompt=prompt,
                patch_path=patch_path,
                started_at=started_at,
                mode=mode,
                error=exc,
                context=context,
                summary_before=summary_before,
                context_plan=context_plan,
            )
            return None
        return IterationPlan(
            iteration=iteration,
            started_at=started_at,
            patch_path=patch_path,
            mode=mode,
            context_plan=context_plan,
            context=context,
            test_summary_before=summary_before,
            proposal=EditProposal(mode=mode, prompt=prompt, raw_output=raw_output, model_call=model_call),
        )

    def _handle_model_error(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        *,
        iteration: int,
        prompt: str,
        patch_path: object,
        started_at: float,
        mode: str,
        error: ModelGenerationError,
        context: ContextBundle,
        summary_before: dict,
        context_plan: object,
    ) -> None:
        state.error = str(error)
        record = self.evaluator.model_error_record(
            iteration=iteration,
            prompt=prompt,
            patch_path=patch_path,
            started_at=started_at,
            mode=mode,
            error=state.error,
            context=context.metadata,
            test_summary_before=summary_before,
            model_call=error.metadata,
        )
        record.context_expansion_level = context_plan.level
        decision = self.retry_policy.after_model_error()
        record.retry_reason = decision.reason
        record.trigger = runtime.trigger
        record.review_feedback_ids = list(runtime.active_review_ids)
        state.iterations.append(record)
        runtime.finished = not decision.continue_repair
        if runtime.finished:
            return
        runtime.feedback = self.prompt_builder.replacement_failure("", state.error)
        logger.warning("iteration %s: model generation failed; retrying if possible", iteration)

    def _apply(self, state: AgentState, runtime: RepairRuntime, plan: IterationPlan):
        backend_result = self.backends[plan.mode].apply(
            state.workspace,
            plan.proposal.raw_output,
            plan.patch_path,
        )
        runtime.patch_applied = runtime.patch_applied or backend_result.applied_to_workspace
        if plan.mode == "patch" or backend_result.success:
            state.patch = backend_result.cleaned_patch
        return backend_result

    def _handle_apply_failure(self, state: AgentState, runtime: RepairRuntime, plan: IterationPlan, result) -> None:
        state.error = result.error
        record = self.evaluator.apply_record(
            iteration=plan.iteration,
            proposal=plan.proposal,
            result=result,
            started_at=plan.started_at,
            context=plan.context.metadata,
            test_summary_before=plan.test_summary_before,
        )
        if result.applied_to_workspace and state.workspace_strategy == "temporary_git_worktree":
            self.workspace_session.rollback()
            record.workspace_action = "rolled_back_after_apply_failure"
        decision = self.retry_policy.after_apply(result)
        record.context_expansion_level = plan.context_plan.level
        record.retry_reason = decision.reason
        record.trigger = runtime.trigger
        record.review_feedback_ids = list(runtime.active_review_ids)
        state.iterations.append(record)
        runtime.feedback = (
            self.prompt_builder.mode_switch_failure(result, decision.next_mode)
            if decision.next_mode != plan.mode
            else self.prompt_builder.apply_failure(result)
        )
        logger.warning(
            "iteration %s: %s; retrying if possible",
            plan.iteration,
            self.prompt_builder.failure_action(result),
        )

    def _verify(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        plan: IterationPlan,
        backend_result,
    ) -> tuple[IterationRecord, CommandResult] | None:
        self.retry_policy.after_apply(backend_result)
        operation = "replacement" if plan.mode == "replacement" else "fix"
        logger.info("iteration %s: running pytest after %s", plan.iteration, operation)
        after = self.test_runner.run(state.workspace)
        state.test_output_after = after.output
        state.success = after.success
        state.error = None if state.success else f"tests still failed after applying {plan.mode}"
        record = self.evaluator.apply_record(
            iteration=plan.iteration,
            proposal=plan.proposal,
            result=backend_result,
            started_at=plan.started_at,
            context=plan.context.metadata,
            test_summary_before=plan.test_summary_before,
            pytest_exit_code=after.exit_code,
            pytest_output=after.output,
            success=state.success,
        )
        if not after.infrastructure_error:
            return record, after

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
        record.context_expansion_level = plan.context_plan.level
        record.trigger = runtime.trigger
        record.review_feedback_ids = list(runtime.active_review_ids)
        state.iterations.append(record)
        runtime.finished = True
        return None

    def _accept_or_retry(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        request: RepairRequest,
        plan: IterationPlan,
        record: IterationRecord,
        after: CommandResult,
    ) -> bool:
        if state.success:
            return self._handle_visible_success(state, runtime, request, plan, record, after)
        self._retry_after_test_failure(state, runtime, plan, record, after)
        return False

    def _handle_visible_success(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        request: RepairRequest,
        plan: IterationPlan,
        record: IterationRecord,
        after: CommandResult,
    ) -> bool:
        checkpoint = self._checkpoint_visible_candidate(state, runtime, plan, record)
        if not self.semantic_review_enabled:
            state.acceptance_status = "disabled"
            return True

        execution, structural_cues, review_decision = self._run_semantic_review(
            state, runtime, request, plan, after
        )
        self._record_review(state, runtime, execution, review_decision, plan, checkpoint)
        return self._apply_review_decision(
            state,
            runtime,
            plan,
            after,
            execution,
            structural_cues,
            review_decision,
        )

    def _checkpoint_visible_candidate(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        plan: IterationPlan,
        record: IterationRecord,
    ) -> str | None:
        state.visible_success = True
        checkpoint = self.workspace_session.checkpoint(plan.iteration, kind="visible_candidate")
        record.context_expansion_level = plan.context_plan.level
        record.trigger = runtime.trigger
        record.review_feedback_ids = list(runtime.active_review_ids)
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
        return checkpoint

    def _run_semantic_review(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        request: RepairRequest,
        plan: IterationPlan,
        after: CommandResult,
    ) -> tuple[ReviewExecution, tuple[dict, ...], ReviewDecision]:
        runtime.review_index += 1
        candidate_diff = self.workspace_session.candidate_diff()
        review_context = self.review_context_provider.build(state.workspace, candidate_diff)
        logger.info("semantic review %s: reviewing visible-pass candidate", runtime.review_index)
        execution = self.semantic_reviewer.review(
            ReviewRequest(
                task=request.task,
                candidate_diff=candidate_diff,
                visible_test_output=after.output,
                context=review_context,
                review_index=runtime.review_index,
            ),
            state.workspace,
        )
        error = execution.model_error or execution.parse_error
        structural_cues = tuple(
            cue for cue in review_context.metadata.get("structural_risk_cues", []) if cue.get("id")
        )
        review_decision = self.review_policy.decide(
            execution.outcome,
            state.semantic_revisions_used,
            error=error,
            structural_cue_categories=tuple(
                str(cue.get("category")) for cue in structural_cues if cue.get("category")
            ),
            structural_cue_ids=tuple(str(cue["id"]) for cue in structural_cues),
        )
        if review_decision.action == "revise" and plan.iteration >= request.max_iterations:
            review_decision = ReviewDecision(
                "needs_review",
                "edit iteration budget exhausted",
                review_decision.blocking_risk_ids,
            )
        return execution, structural_cues, review_decision

    def _record_review(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        execution: ReviewExecution,
        review_decision: ReviewDecision,
        plan: IterationPlan,
        checkpoint: str | None,
    ) -> None:
        state.reviews.append(
            ReviewRecord(
                review_index=runtime.review_index,
                based_on_iteration=plan.iteration,
                prompt=execution.prompt,
                raw_model_output=execution.raw_output,
                parsed_outcome=asdict(execution.outcome) if execution.outcome is not None else None,
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

    def _apply_review_decision(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        plan: IterationPlan,
        after: CommandResult,
        execution: ReviewExecution,
        structural_cues: tuple[dict, ...],
        review_decision: ReviewDecision,
    ) -> bool:
        error = execution.model_error or execution.parse_error
        if review_decision.action in {"accept", "accept_with_warnings"}:
            state.acceptance_status = (
                "accepted_with_warnings" if review_decision.action == "accept_with_warnings" else "accepted"
            )
            state.success = True
            state.error = None
            return True
        if review_decision.action == "revise" and execution.outcome is not None:
            runtime.active_review_feedback, runtime.active_review_ids = build_review_feedback(
                execution.outcome,
                self.review_max_feedback_chars,
                review_decision.blocking_risk_ids,
                structural_cues,
            )
            runtime.feedback = runtime.active_review_feedback
            runtime.current_test_output = after.output
            runtime.trigger = "semantic_revision"
            state.semantic_revisions_used += 1
            state.success = False
            state.acceptance_status = "revising"
            logger.info("semantic review %s: requesting one bounded revision", runtime.review_index)
            return False
        state.success = False
        state.acceptance_status = (
            "review_error"
            if error
            else "abstained"
            if execution.outcome and execution.outcome.verdict == "abstain"
            else "rejected"
        )
        state.error = None
        return True

    def _retry_after_test_failure(
        self,
        state: AgentState,
        runtime: RepairRuntime,
        plan: IterationPlan,
        record: IterationRecord,
        after: CommandResult,
    ) -> None:
        failure_type = str((record.iteration_result or {}).get("failure_type") or "unknown")
        decision = self.retry_policy.after_test_failure(record.iteration_result)
        rolled_back = decision.rollback and state.workspace_strategy == "temporary_git_worktree"
        if rolled_back:
            self.workspace_session.rollback()
            record.workspace_action = f"rolled_back_{failure_type}"
        else:
            self.workspace_session.checkpoint(plan.iteration)
            record.workspace_action = (
                "checkpointed_partial"
                if state.workspace_strategy == "temporary_git_worktree"
                else "kept_in_place"
            )
            runtime.current_test_output = after.output
        if decision.expand_context:
            self.context_policy.expand(decision.reason)
        record.context_expansion_level = plan.context_plan.level
        record.retry_reason = decision.reason
        record.trigger = runtime.trigger
        record.review_feedback_ids = list(runtime.active_review_ids)
        state.iterations.append(record)
        test_feedback = self.prompt_builder.semantic_test_failure(
            mode=plan.mode,
            failure_type=failure_type,
            delta=record.failure_delta or {},
            test_output=after.output,
            rolled_back=rolled_back,
            context_expansion_level=self.context_policy.level,
        )
        runtime.feedback = (
            f"{runtime.active_review_feedback}\n\n{test_feedback}"
            if runtime.active_review_feedback
            else test_feedback
        )
        logger.info("iteration %s: tests still failed; retrying if possible", plan.iteration)

    def _mark_iteration_limit(self, state: AgentState, request: RepairRequest) -> None:
        if state.visible_success and self.semantic_review_enabled:
            state.success = False
            state.acceptance_status = "rejected"
            state.error = None
            return
        if state.error is None:
            state.error = "agent did not produce a successful patch"
        state.error = f"{state.error}; reached max_iterations={request.max_iterations}"

    def _close_workspace(self) -> None:
        try:
            self.workspace_session.close()
        except (OSError, RuntimeError) as exc:
            logger.warning("temporary workspace cleanup failed: %s", exc)

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
