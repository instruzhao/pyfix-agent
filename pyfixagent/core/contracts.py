from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


RepairMode = Literal["patch", "replacement"]


@dataclass(frozen=True)
class RepairRequest:
    """Stable input boundary for a repair run."""

    task: str
    workspace: Path
    max_iterations: int


@dataclass
class ContextBundle:
    """Prompt-ready source context and trace metadata."""

    rendered: str
    metadata: dict


@dataclass(frozen=True)
class EditProposal:
    """A model response before it is trusted or applied."""

    mode: RepairMode
    prompt: str
    raw_output: str
    model_call: dict = field(default_factory=dict)


@dataclass
class ApplyResult:
    """Normalized result returned by every edit backend."""

    mode: RepairMode
    success: bool
    raw_output: str
    cleaned_patch: str = ""
    patch_path: str = ""
    check_success: bool = False
    check_error: str = ""
    apply_success: bool = False
    apply_error: str = ""
    command: str = ""
    error: str | None = None
    failure_stage: str | None = None
    applied_to_workspace: bool = False
    replacement_edits: list[dict] | None = None
    replacement_success: bool | None = None
    replacement_error: str | None = None


@dataclass(frozen=True)
class RetryDecision:
    """Pure decision emitted by the retry policy."""

    continue_repair: bool
    next_mode: RepairMode
    reason: str
    rollback: bool = False
    checkpoint: bool = False
    expand_context: bool = False
