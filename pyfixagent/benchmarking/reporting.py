from pyfixagent.benchmarking.metrics import summarize_runs


def render_markdown(report: dict) -> str:
    summary = report["summary"]
    lines = [
        "# PyFixAgent Benchmark Report",
        "",
        f"- Runs: {summary['runs']}",
        f"- Final success rate: {summary['success_rate']:.1%}",
        f"- Visible-test success rate: {summary['visible_success_rate']:.1%}",
        f"- Candidate holdout success rate: {summary.get('candidate_success_rate', 0):.1%}",
        f"- Review acceptance rate: {summary.get('review_acceptance_rate', 0):.1%}",
        f"- Holdout success rate: {summary['holdout_success_rate']:.1%}",
        f"- Success@1: {summary['success_at_1']:.1%}",
        f"- Pass@k: {summary['pass_at_k']:.1%}",
        f"- Average iterations: {summary['average_iterations']}",
        f"- Regression rate: {summary['regression_rate']:.1%}",
        f"- Repair tokens (input/output): {summary.get('repair_input_tokens', 0)}/{summary.get('repair_output_tokens', 0)}",
        f"- Review tokens (input/output): {summary.get('review_input_tokens', 0)}/{summary.get('review_output_tokens', 0)}",
        f"- Repository success rate: {percentage(summary.get('repository_success_rate'))}",
        f"- Legacy success rate: {percentage(summary.get('legacy_success_rate'))}",
        f"- Repository A/B wins/losses/ties: {summary.get('repository_ab_win_count', 0)}/{summary.get('repository_ab_loss_count', 0)}/{summary.get('repository_ab_tie_count', 0)}",
        "",
        "| Case | Variant | Strategy | Repeat | Visible | Review | Holdout | Final | Iterations | Failure type | Repair tokens | Review tokens |",
        "|---|---|---|---:|---|---|---|---|---:|---|---:|---:|",
    ]
    for run in report["runs"]:
        lines.append(
            f"| {run['case_id']} | {run.get('variant', 'default')} | {run['strategy']} | {run['repetition']} | "
            f"{yes_no(run.get('visible_success'))} | {run.get('acceptance_status', 'n/a')} | "
            f"{yes_no(run.get('holdout_success'))} | "
            f"{yes_no(run.get('success'))} | {run['iterations']} | "
            f"{run.get('failure_type') or ''} | "
            f"{int(run.get('repair_input_tokens', 0)) + int(run.get('repair_output_tokens', 0))} | "
            f"{int(run.get('review_input_tokens', 0)) + int(run.get('review_output_tokens', 0))} |"
        )
    return "\n".join(lines) + "\n"


def yes_no(value) -> str:
    if value is None:
        return "n/a"
    return "yes" if value else "no"


def percentage(value) -> str:
    return "n/a" if value is None else f"{float(value):.1%}"


__all__ = ["render_markdown", "summarize_runs"]
