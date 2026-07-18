from dataclasses import dataclass


@dataclass
class IterationRecord:
    iteration: int
    prompt: str
    raw_model_output: str
    cleaned_patch: str
    patch_path: str
    apply_check_success: bool
    apply_check_error: str
    apply_success: bool
    apply_error: str
    pytest_exit_code: int | None
    pytest_output: str
    success: bool
    duration_seconds: float
    mode: str = "patch"
    model_output_type: str = "patch"
    replacement_raw_output: str | None = None
    replacement_edits: list[dict] | None = None
    replacement_success: bool | None = None
    replacement_error: str | None = None
    patch_command: str = ""
    context: dict | None = None
    test_summary_before: dict | None = None
    test_summary_after: dict | None = None
    failure_delta: dict | None = None
    iteration_result: dict | None = None
    generated_diff: str = ""
    model_output: dict | None = None
    apply: dict | None = None
    edit_summary: dict | None = None
    model_call: dict | None = None
    workspace_action: str | None = None
    retry_reason: str | None = None
    context_expansion_level: int = 0
    trigger: str = "pytest_failure"
    review_feedback_ids: list[str] | None = None
    candidate_checkpoint: str | None = None


@dataclass
class ReviewRecord:
    review_index: int
    based_on_iteration: int
    prompt: str
    raw_model_output: str
    parsed_outcome: dict | None
    parse_error: str | None
    model_error: str | None
    model_calls: list[dict]
    context: dict
    policy_action: str
    policy_reason: str
    blocking_risk_ids: list[str]
    candidate_checkpoint: str | None = None


@dataclass
class AgentResult:
    task: str
    workspace: str
    success: bool
    patch_applied: bool
    test_output_before: str
    test_output_after: str
    patch: str
    iterations: list[IterationRecord]
    workspace_strategy: str = "incremental_repair"
    final_patch_command: str = ""
    error: str | None = None
    environment: dict | None = None
    final_summary: dict | None = None
    trace_schema_version: str = "1.5"
    workspace_state: dict | None = None
    final_patch_path: str = ""
    visible_success: bool = False
    acceptance_status: str = "not_run"
    candidate_patch: str = ""
    candidate_patch_path: str = ""
    reviews: list[ReviewRecord] | None = None
    semantic_revisions_used: int = 0
