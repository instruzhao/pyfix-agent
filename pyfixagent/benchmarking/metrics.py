from collections import Counter


def summarize_runs(runs: list[dict]) -> dict:
    total = len(runs)
    successes = sum(bool(run.get("success")) for run in runs)
    visible_successes = sum(bool(run.get("visible_success")) for run in runs)
    holdout_evaluated = [run for run in runs if run.get("holdout_success") is not None]
    holdout_successes = sum(bool(run.get("holdout_success")) for run in holdout_evaluated)
    case_keys = {(run.get("case_id"), run.get("strategy")) for run in runs}
    passed_cases = sum(
        any(run.get("success") for run in runs if (run.get("case_id"), run.get("strategy")) == key)
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
    return {
        "runs": total,
        "successful_runs": successes,
        "success_rate": rate(successes, total),
        "visible_success_rate": rate(visible_successes, total),
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
    }


def rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator else 0.0
