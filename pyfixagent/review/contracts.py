from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from pyfixagent.core.contracts import ContextBundle


ReviewVerdict = Literal["accept", "revise", "abstain"]
ReviewAction = Literal["accept", "accept_with_warnings", "revise", "needs_review"]


@dataclass(frozen=True)
class ReviewRisk:
    risk_id: str
    category: str
    severity: str
    reason: str
    contract_id: str | None = None
    evidence: tuple[dict, ...] = ()
    counterexamples: tuple[dict, ...] = ()


@dataclass(frozen=True)
class ReviewOutcome:
    verdict: ReviewVerdict
    summary: str
    contracts: tuple[dict, ...] = ()
    risks: tuple[ReviewRisk, ...] = ()
    repair_feedback: str = ""

    @property
    def blocking_risks(self) -> tuple[ReviewRisk, ...]:
        return tuple(risk for risk in self.risks if risk.severity == "blocking")


@dataclass(frozen=True)
class ReviewRequest:
    task: str
    candidate_diff: str
    visible_test_output: str
    context: ContextBundle
    review_index: int


@dataclass(frozen=True)
class ReviewDecision:
    action: ReviewAction
    reason: str
    blocking_risk_ids: tuple[str, ...] = ()


@dataclass
class ReviewExecution:
    prompt: str
    raw_output: str = ""
    outcome: ReviewOutcome | None = None
    parse_error: str | None = None
    model_error: str | None = None
    model_calls: list[dict] = field(default_factory=list)
    context: dict = field(default_factory=dict)
