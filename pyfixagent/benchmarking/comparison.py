from __future__ import annotations

from collections import Counter
import math


def compare_reports(baseline: dict, candidate: dict) -> dict:
    """Compare matched benchmark trials without treating unmatched runs as evidence."""
    baseline_runs = _index_runs(baseline.get("runs", []), "baseline")
    candidate_runs = _index_runs(candidate.get("runs", []), "candidate")
    matched_keys = sorted(baseline_runs.keys() & candidate_runs.keys())
    baseline_only = sorted(baseline_runs.keys() - candidate_runs.keys())
    candidate_only = sorted(candidate_runs.keys() - baseline_runs.keys())
    pairs = [(baseline_runs[key], candidate_runs[key]) for key in matched_keys]
    wins = sum(not bool(before.get("success")) and bool(after.get("success")) for before, after in pairs)
    losses = sum(bool(before.get("success")) and not bool(after.get("success")) for before, after in pairs)
    ties = len(pairs) - wins - losses
    before_successes = sum(bool(before.get("success")) for before, _ in pairs)
    after_successes = sum(bool(after.get("success")) for _, after in pairs)
    before_tokens = sum(_tokens(before) for before, _ in pairs)
    after_tokens = sum(_tokens(after) for _, after in pairs)
    before_seconds = sum(float(before.get("duration_seconds", 0.0)) for before, _ in pairs)
    after_seconds = sum(float(after.get("duration_seconds", 0.0)) for _, after in pairs)
    return {
        "schema_version": 1,
        "protocol_compatibility": _protocol_compatibility(baseline, candidate),
        "matched_runs": len(pairs),
        "comparison_complete": bool(pairs) and not baseline_only and not candidate_only,
        "baseline_only_runs": len(baseline_only),
        "candidate_only_runs": len(candidate_only),
        "wins": wins,
        "losses": losses,
        "ties": ties,
        "mcnemar_exact_pvalue": _mcnemar_exact(wins, losses),
        "baseline_success_rate": _rate(before_successes, len(pairs)),
        "candidate_success_rate": _rate(after_successes, len(pairs)),
        "success_rate_delta": round(_rate(after_successes, len(pairs)) - _rate(before_successes, len(pairs)), 4),
        "baseline_total_tokens": before_tokens,
        "candidate_total_tokens": after_tokens,
        "token_delta": after_tokens - before_tokens,
        "baseline_total_seconds": round(before_seconds, 3),
        "candidate_total_seconds": round(after_seconds, 3),
        "duration_delta_seconds": round(after_seconds - before_seconds, 3),
        "failure_delta": _failure_delta(pairs),
        "unmatched": {
            "baseline_only": [_render_key(key) for key in baseline_only],
            "candidate_only": [_render_key(key) for key in candidate_only],
        },
    }


def render_comparison_markdown(comparison: dict) -> str:
    compatibility = comparison["protocol_compatibility"]
    lines = [
        "# PyFixAgent Benchmark Comparison",
        "",
        f"- Protocol compatible: {'yes' if compatibility['compatible'] else 'no'}",
        f"- Matched runs: {comparison['matched_runs']}",
        f"- Comparison complete: {'yes' if comparison['comparison_complete'] else 'no'}",
        f"- Candidate wins/losses/ties: {comparison['wins']}/{comparison['losses']}/{comparison['ties']}",
        f"- Baseline success rate: {comparison['baseline_success_rate']:.1%}",
        f"- Candidate success rate: {comparison['candidate_success_rate']:.1%}",
        f"- Success-rate delta: {comparison['success_rate_delta']:+.1%}",
        f"- Exact paired p-value: {comparison['mcnemar_exact_pvalue']:.4f}",
        f"- Token delta: {comparison['token_delta']:+d}",
        f"- Duration delta: {comparison['duration_delta_seconds']:+.3f}s",
    ]
    if compatibility["differences"]:
        lines.extend(["", "## Protocol differences", ""])
        lines.extend(f"- {item}" for item in compatibility["differences"])
    if compatibility.get("context_differences"):
        lines.extend(["", "## Run-context differences", ""])
        lines.extend(f"- {item}" for item in compatibility["context_differences"])
    if comparison["failure_delta"]:
        lines.extend(["", "## Failure-count delta", "", "| Failure type | Delta |", "|---|---:|"])
        lines.extend(
            f"| {failure_type} | {delta:+d} |"
            for failure_type, delta in comparison["failure_delta"].items()
        )
    return "\n".join(lines) + "\n"


def _run_key(run: dict) -> tuple[str, str, str, int]:
    return (
        str(run.get("case_id", "")),
        str(run.get("strategy", "")),
        str(run.get("variant", "default")),
        int(run.get("repetition", 1)),
    )


def _index_runs(runs: list[dict], label: str) -> dict[tuple[str, str, str, int], dict]:
    indexed = {}
    for run in runs:
        key = _run_key(run)
        if key in indexed:
            raise ValueError(f"duplicate {label} trial identity: {_render_key(key)}")
        indexed[key] = run
    return indexed


def _render_key(key: tuple[str, str, str, int]) -> dict:
    return {"case_id": key[0], "strategy": key[1], "variant": key[2], "repetition": key[3]}


def _tokens(run: dict) -> int:
    return int(run.get("input_tokens", 0)) + int(run.get("output_tokens", 0))


def _rate(successes: int, total: int) -> float:
    return round(successes / total, 4) if total else 0.0


def _mcnemar_exact(wins: int, losses: int) -> float:
    discordant = wins + losses
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, index) for index in range(min(wins, losses) + 1))
    return round(min(1.0, 2 * tail / (2**discordant)), 6)


def _protocol_compatibility(baseline: dict, candidate: dict) -> dict:
    before = baseline.get("protocol", {})
    after = candidate.get("protocol", {})
    fields = ("manifest_sha256", "case_ids", "repeat", "strategies", "repository_modes")
    differences = []
    for field in fields:
        if field not in before or field not in after:
            differences.append(f"{field}: missing protocol metadata")
        elif before[field] != after[field]:
            differences.append(f"{field}: {before[field]!r} -> {after[field]!r}")
    context_fields = (
        "project_revision",
        "project_dirty",
        "config_sha256",
        "model",
        "review_model",
        "sandbox_backend",
        "container_engine",
        "container_image",
        "python",
        "platform",
    )
    context_differences = [
        f"{field}: {before.get(field)!r} -> {after.get(field)!r}"
        for field in context_fields
        if before.get(field) != after.get(field)
    ]
    return {
        "compatible": not differences,
        "differences": differences,
        "context_differences": context_differences,
    }


def _failure_delta(pairs: list[tuple[dict, dict]]) -> dict[str, int]:
    before = Counter(str(run.get("failure_type") or "success") for run, _ in pairs)
    after = Counter(str(run.get("failure_type") or "success") for _, run in pairs)
    keys = sorted(before.keys() | after.keys())
    return {key: after[key] - before[key] for key in keys if after[key] != before[key]}
