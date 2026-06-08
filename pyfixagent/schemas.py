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
