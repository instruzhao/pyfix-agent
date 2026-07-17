from pyfixagent.review.contracts import ReviewOutcome


def build_review_feedback(
    outcome: ReviewOutcome,
    max_chars: int = 3000,
    risk_ids: tuple[str, ...] = (),
    structural_cues: tuple[dict, ...] = (),
) -> tuple[str, tuple[str, ...]]:
    selected = tuple(
        risk
        for risk in outcome.risks
        if risk.risk_id in risk_ids or not risk_ids and risk.severity == "blocking"
    )
    lines = [
        "Visible tests pass, but an independent semantic review found validated blocking risks.",
        "Revise the current candidate without weakening behavior already covered by visible tests.",
    ]
    for risk in selected:
        lines.append(f"[{risk.risk_id}] {risk.category}: {risk.reason}")
        for counterexample in risk.counterexamples:
            lines.append(
                "Counterexample shape: "
                f"{counterexample['input_shape']}; required property: "
                f"{counterexample['expected_property']}"
            )
    selected_cues = [
        cue for cue in structural_cues if f"cue:{cue.get('id')}" in risk_ids
    ]
    for cue in selected_cues:
        lines.append(f"[cue:{cue.get('id')}] {cue.get('description')}")
    text = "\n".join(lines)
    selected_ids = tuple(risk.risk_id for risk in selected) + tuple(
        f"cue:{cue.get('id')}" for cue in selected_cues
    )
    return text[: max(200, max_chars)], selected_ids
