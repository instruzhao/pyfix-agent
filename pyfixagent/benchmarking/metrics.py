from collections import Counter


def summarize_runs(runs: list[dict]) -> dict:
    total = len(runs)
    successes = sum(bool(run.get("success")) for run in runs)
    visible_successes = sum(bool(run.get("visible_success")) for run in runs)
    candidate_successes = sum(bool(run.get("candidate_success")) for run in runs)
    accepted = sum(bool(run.get("agent_accepted")) for run in runs)
    holdout_evaluated = [run for run in runs if run.get("holdout_success") is not None]
    holdout_successes = sum(bool(run.get("holdout_success")) for run in holdout_evaluated)
    case_keys = {
        (run.get("case_id"), run.get("strategy"), run.get("variant", "default"))
        for run in runs
    }
    passed_cases = sum(
        any(
            run.get("success")
            for run in runs
            if (run.get("case_id"), run.get("strategy"), run.get("variant", "default")) == key
        )
        for key in case_keys
    )
    first_runs = [run for run in runs if int(run.get("repetition", 1)) == 1]
    failure_counts = Counter(
        str(run.get("failure_type") or "unknown") for run in runs if not run.get("success")
    )
    iteration_results = [
        failure_type
        for run in runs
        for failure_type in (run.get("iteration_failure_types") or [])
    ]
    repository_runs = [run for run in runs if run.get("repository_context_enabled") is True]
    legacy_runs = [run for run in runs if run.get("repository_context_enabled") is False]
    context_recall_values = _numeric_values(runs, "context_required_recall")
    context_precision_values = _numeric_values(runs, "context_precision")
    distractor_rate_values = _numeric_values(runs, "context_distractor_rate")
    ab = _ab_summary(runs)
    return {
        "runs": total,
        "successful_runs": successes,
        "success_rate": rate(successes, total),
        "visible_success_rate": rate(visible_successes, total),
        "candidate_success_rate": rate(candidate_successes, total),
        "review_acceptance_rate": rate(accepted, total),
        "holdout_success_rate": rate(holdout_successes, len(holdout_evaluated)),
        "case_strategy_pairs": len(case_keys),
        "pass_at_k": rate(passed_cases, len(case_keys)),
        "success_at_1": rate(sum(bool(run.get("success")) for run in first_runs), len(first_runs)),
        "average_iterations": round(
            sum(int(run.get("iterations", 0)) for run in runs) / total, 3
        ) if total else 0.0,
        "regression_rate": rate(iteration_results.count("regression"), len(iteration_results)),
        "no_progress_rate": rate(iteration_results.count("no_progress"), len(iteration_results)),
        "failure_counts": dict(sorted(failure_counts.items())),
        "policy_violation_count": sum(int(run.get("policy_violation_count", 0)) for run in runs),
        "total_prompt_chars": sum(int(run.get("prompt_chars", 0)) for run in runs),
        "total_input_tokens": sum(int(run.get("input_tokens", 0)) for run in runs),
        "total_output_tokens": sum(int(run.get("output_tokens", 0)) for run in runs),
        "repair_input_tokens": sum(int(run.get("repair_input_tokens", 0)) for run in runs),
        "repair_output_tokens": sum(int(run.get("repair_output_tokens", 0)) for run in runs),
        "review_input_tokens": sum(int(run.get("review_input_tokens", 0)) for run in runs),
        "review_output_tokens": sum(int(run.get("review_output_tokens", 0)) for run in runs),
        "repair_model_seconds": round(
            sum(float(run.get("repair_model_seconds", 0.0)) for run in runs), 3
        ),
        "review_model_seconds": round(
            sum(float(run.get("review_model_seconds", 0.0)) for run in runs), 3
        ),
        "average_duration_seconds": round(
            sum(float(run.get("duration_seconds", 0.0)) for run in runs) / total, 3
        ) if total else 0.0,
        "review_count": sum(int(run.get("review_count", 0)) for run in runs),
        "semantic_revision_count": sum(
            int(run.get("semantic_revisions_used", 0)) for run in runs
        ),
        "false_accept_count": sum(run.get("failure_type") == "false_accept" for run in runs),
        "false_reject_count": sum(run.get("failure_type") == "false_reject" for run in runs),
        "repository_run_count": len(repository_runs),
        "repository_success_rate": (
            rate(sum(bool(run.get("success")) for run in repository_runs), len(repository_runs))
            if repository_runs
            else None
        ),
        "legacy_run_count": len(legacy_runs),
        "legacy_success_rate": (
            rate(sum(bool(run.get("success")) for run in legacy_runs), len(legacy_runs))
            if legacy_runs
            else None
        ),
        "repository_context_builds": sum(
            int(run.get("repository_context_builds", 0)) for run in runs
        ),
        "repository_cache_hits": sum(int(run.get("repository_cache_hits", 0)) for run in runs),
        "repository_index_seconds": round(
            sum(float(run.get("repository_index_seconds", 0.0)) for run in runs), 3
        ),
        "repository_build_seconds": round(
            sum(float(run.get("repository_build_seconds", 0.0)) for run in runs), 3
        ),
        "repository_budget_truncation_count": sum(
            int(run.get("repository_budget_truncations", 0)) for run in runs
        ),
        "repository_related_file_count": sum(
            int(run.get("repository_related_file_count", 0)) for run in runs
        ),
        "repository_max_estimated_tokens": max(
            (int(run.get("repository_max_estimated_tokens", 0)) for run in runs),
            default=0,
        ),
        "average_context_required_recall": _average(context_recall_values),
        "average_context_precision": _average(context_precision_values),
        "average_context_distractor_rate": _average(distractor_rate_values),
        **ab,
    }


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0


def _numeric_values(runs: list[dict], key: str) -> list[float]:
    return [float(run[key]) for run in runs if run.get(key) is not None]


def _average(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 4) if values else None


def _ab_summary(runs: list[dict]) -> dict:
    pairs: dict[tuple, dict[bool, dict]] = {}
    for run in runs:
        enabled = run.get("repository_context_enabled")
        if enabled is None:
            continue
        key = (run.get("case_id"), run.get("strategy"), int(run.get("repetition", 1)))
        pairs.setdefault(key, {})[bool(enabled)] = run
    complete = [pair for pair in pairs.values() if True in pair and False in pair]
    wins = sum(bool(pair[True].get("success")) and not pair[False].get("success") for pair in complete)
    losses = sum(not pair[True].get("success") and bool(pair[False].get("success")) for pair in complete)
    return {
        "repository_ab_pair_count": len(complete),
        "repository_ab_win_count": wins,
        "repository_ab_loss_count": losses,
        "repository_ab_tie_count": len(complete) - wins - losses,
    }
