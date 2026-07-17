from pyfixagent.review.contracts import ReviewDecision, ReviewOutcome


class ReviewPolicy:
    """Turns a validated review outcome into a workflow action."""

    def __init__(self, max_semantic_revisions: int = 1):
        self.max_semantic_revisions = max(0, max_semantic_revisions)

    def decide(
        self,
        outcome: ReviewOutcome | None,
        revisions_used: int,
        error: str | None = None,
        structural_cue_categories: tuple[str, ...] = (),
        structural_cue_ids: tuple[str, ...] = (),
    ):
        if outcome is None:
            return ReviewDecision("needs_review", error or "semantic review did not produce an outcome")
        blockers = tuple(risk.risk_id for risk in outcome.blocking_risks)
        promoted = tuple(
            risk.risk_id
            for risk in outcome.risks
            if risk.severity == "warning"
            and risk.category in structural_cue_categories
            and risk.evidence
            and risk.counterexamples
        )
        actionable = blockers or promoted
        if actionable:
            if revisions_used < self.max_semantic_revisions:
                reason = (
                    "validated blocking semantic risks"
                    if blockers
                    else "evidence-based warning matches a structural risk cue"
                )
                return ReviewDecision("revise", reason, actionable)
            return ReviewDecision("needs_review", "semantic revision budget exhausted", actionable)
        cue_risks = tuple(f"cue:{cue_id}" for cue_id in structural_cue_ids)
        if cue_risks:
            if revisions_used < self.max_semantic_revisions:
                return ReviewDecision(
                    "revise",
                    "unmitigated deterministic structural risk cue",
                    cue_risks,
                )
            return ReviewDecision("needs_review", "structural risk cue remains after revision", cue_risks)
        if outcome.verdict == "abstain":
            return ReviewDecision("needs_review", "reviewer abstained")
        if outcome.verdict == "revise":
            return ReviewDecision("needs_review", "reviewer requested revision without blocking evidence")
        if outcome.risks:
            return ReviewDecision("accept_with_warnings", "no blocking semantic risks")
        return ReviewDecision("accept", "reviewer accepted candidate")
