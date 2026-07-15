from pyfixagent.core.contracts import ApplyResult, RepairMode, RetryDecision


class RetryPolicy:
    """Owns mode switching and retry/stop decisions."""

    def __init__(self, initial_mode: RepairMode):
        if initial_mode not in {"patch", "replacement"}:
            raise ValueError("initial_mode must be 'patch' or 'replacement'")
        self.mode: RepairMode = initial_mode
        self.consecutive_patch_check_failures = 0
        self.consecutive_replacement_apply_failures = 0

    def after_model_error(self) -> RetryDecision:
        return RetryDecision(
            continue_repair=self.mode == "replacement",
            next_mode=self.mode,
            reason="retry_replacement_model_error" if self.mode == "replacement" else "stop_patch_model_error",
        )

    def after_apply(self, result: ApplyResult) -> RetryDecision:
        if result.mode == "patch" and result.failure_stage == "check":
            self.consecutive_patch_check_failures += 1
            if self.consecutive_patch_check_failures >= 2:
                self.mode = "replacement"
                return RetryDecision(True, self.mode, "switch_to_replacement_after_patch_checks")
        elif result.mode == "patch" and result.applied_to_workspace:
            self.consecutive_patch_check_failures = 0
        if result.mode == "replacement" and result.failure_stage == "apply":
            self.consecutive_replacement_apply_failures += 1
            lost_source_anchor = "old text was not found" in str(result.error or "").lower()
            if lost_source_anchor or self.consecutive_replacement_apply_failures >= 2:
                self.mode = "patch"
                self.consecutive_patch_check_failures = 0
                reason = (
                    "switch_to_patch_after_lost_replacement_anchor"
                    if lost_source_anchor
                    else "switch_to_patch_after_replacement_apply_failures"
                )
                return RetryDecision(True, self.mode, reason)
        elif result.mode == "replacement" and result.applied_to_workspace:
            self.consecutive_replacement_apply_failures = 0
        return RetryDecision(True, self.mode, f"retry_after_{result.failure_stage or 'apply'}")

    def after_test_failure(self) -> RetryDecision:
        return RetryDecision(True, self.mode, "retry_after_test_failure")
