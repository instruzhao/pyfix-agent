from __future__ import annotations

import argparse
from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import tempfile

from pyfixagent.sandbox.container_sandbox import ContainerPolicy, ContainerSandbox


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure runner startup latency and exercise enforceable write limits."
    )
    parser.add_argument("--engine", choices=["docker", "podman"], default="docker")
    parser.add_argument("--image", default="pyfixagent-runner:0.7.2")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/container-qualification"))
    parser.add_argument("--probe-limits", action="store_true")
    return parser.parse_args(argv)


def run_qualification(
    *,
    engine: str,
    image: str,
    repeat: int,
    probe_limits: bool,
    workspace_parent: Path | None = None,
) -> dict:
    if repeat < 2:
        raise ValueError("repeat must be at least 2 so first and repeated runs are distinguishable")
    parent = Path(workspace_parent or Path.cwd() / "tmp")
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="runner-qualification-", dir=parent) as temporary:
        workspace = Path(temporary)
        (workspace / "test_smoke.py").write_text(
            "def test_runner_smoke():\n    assert 6 * 7 == 42\n", encoding="utf-8"
        )
        policy = ContainerPolicy(engine=engine, image=image)
        sandbox = ContainerSandbox(workspace, timeout_seconds=60, policy=policy)
        runs = []
        workloads = {
            "python_startup": ["python", "-c", "print('runner-ready')"],
            "pytest_startup": ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"],
        }
        for workload, command in workloads.items():
            for repetition in range(1, repeat + 1):
                result = sandbox.run(command)
                runs.append(
                    {
                        "workload": workload,
                        "repetition": repetition,
                        "phase": "first" if repetition == 1 else "repeated",
                        "success": result.exit_code == 0,
                        "exit_code": result.exit_code,
                        "duration_seconds": round(result.duration, 6),
                        "infrastructure_error": result.infrastructure_error,
                        "policy_violation": result.policy_violation,
                    }
                )
        probes = _run_limit_probes(workspace, policy) if probe_limits else {}
        return {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "runtime": sandbox.environment_metadata(),
            "repeat": repeat,
            "summary": _summarize_runs(runs),
            "runs": runs,
            "limit_probes": probes,
            "limitations": [
                "Timings include client and ephemeral-container overhead on this host.",
                "Every run uses the locally cached image; image pull time is excluded.",
                "The first Python measurement also includes this sandbox instance's one-time runtime preflight.",
                "Bind-mounted workspace growth is monitored, not kernel- or filesystem-quota enforced.",
                "A create/delete burst can disappear between sampling and the final scan.",
            ],
        }


def render_markdown(report: dict) -> str:
    lines = [
        "# PyFixAgent Runner Qualification",
        "",
        f"- Engine: {report['runtime'].get('engine')}",
        f"- Engine version: {report['runtime'].get('engine_server_version') or 'unavailable'}",
        f"- Image: {report['runtime'].get('image_requested')}",
        f"- Resolved image: {report['runtime'].get('image_resolved') or 'unavailable'}",
        f"- Runs successful: {report['summary']['successful_runs']}/{report['summary']['runs']}",
        "",
        "| Workload | First | Repeated mean | Repeated p50 | Repeated p95 |",
        "|---|---:|---:|---:|---:|",
    ]
    for workload, metrics in report["summary"]["workloads"].items():
        lines.append(
            f"| {workload} | {metrics['first_seconds']:.3f}s | "
            f"{metrics['repeated_mean_seconds']:.3f}s | {metrics['repeated_p50_seconds']:.3f}s | "
            f"{metrics['repeated_p95_seconds']:.3f}s |"
        )
    if report["limit_probes"]:
        probes = report["limit_probes"]
        lines.extend(
            [
                "",
                "## Write-limit probes",
                "",
                f"- Persistent over-budget write detected: {str(probes['persistent_write_detected']).lower()}",
                f"- Transient create/delete burst detected: {str(probes['transient_burst_detected']).lower()}",
                "- The transient result is informational and documents the remaining bind-mount quota gap.",
            ]
        )
    lines.extend(["", "## Scope", ""])
    lines.extend(f"- {item}" for item in report["limitations"])
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = run_qualification(
        engine=args.engine,
        image=args.image,
        repeat=args.repeat,
        probe_limits=args.probe_limits,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "qualification.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    markdown = render_markdown(report)
    (args.output_dir / "qualification.md").write_text(markdown, encoding="utf-8")
    print(markdown)
    persistent_ok = not args.probe_limits or report["limit_probes"]["persistent_write_detected"]
    return 0 if report["summary"]["successful_runs"] == report["summary"]["runs"] and persistent_ok else 1


def cli() -> None:
    raise SystemExit(main())


def _summarize_runs(runs: list[dict]) -> dict:
    workloads = {}
    for workload in sorted({run["workload"] for run in runs}):
        selected = [run for run in runs if run["workload"] == workload]
        first = [float(run["duration_seconds"]) for run in selected if run["phase"] == "first"]
        repeated = [float(run["duration_seconds"]) for run in selected if run["phase"] == "repeated"]
        workloads[workload] = {
            "first_seconds": round(first[0], 6),
            "repeated_mean_seconds": round(statistics.fmean(repeated), 6),
            "repeated_p50_seconds": round(statistics.median(repeated), 6),
            "repeated_p95_seconds": round(_percentile(repeated, 0.95), 6),
        }
    return {
        "runs": len(runs),
        "successful_runs": sum(bool(run["success"]) for run in runs),
        "workloads": workloads,
    }


def _percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def _run_limit_probes(workspace: Path, base_policy: ContainerPolicy) -> dict:
    probe_policy = replace(
        base_policy,
        workspace_write_limit="8k",
        file_size_limit="64m",
    )
    sandbox = ContainerSandbox(workspace, timeout_seconds=30, policy=probe_policy)
    persistent = sandbox.run(
        ["python", "-c", "from pathlib import Path; Path('persistent.bin').write_bytes(b'x'*32768)"]
    )
    (workspace / "persistent.bin").unlink(missing_ok=True)
    transient = sandbox.run(
        [
            "python",
            "-c",
            "from pathlib import Path; p=Path('transient.bin'); p.write_bytes(b'x'*32768); p.unlink()",
        ]
    )
    return {
        "persistent_write_detected": bool(persistent.policy_violation),
        "persistent_exit_code": persistent.exit_code,
        "transient_burst_detected": bool(transient.policy_violation),
        "transient_exit_code": transient.exit_code,
    }


if __name__ == "__main__":
    cli()
