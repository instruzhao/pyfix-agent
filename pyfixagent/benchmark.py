"""Compatibility facade for the modular v0.4 benchmark implementation."""

from pyfixagent.benchmarking.cli import cli, main, parse_args
from pyfixagent.benchmarking.comparison import compare_reports, render_comparison_markdown
from pyfixagent.benchmarking.contracts import BenchmarkCase, build_generic_task
from pyfixagent.benchmarking.manifest import load_manifest, validate_benchmark_cases
from pyfixagent.benchmarking.metrics import summarize_runs
from pyfixagent.benchmarking.reporting import render_markdown
from pyfixagent.benchmarking.runner import run_benchmark

__all__ = [
    "BenchmarkCase",
    "build_generic_task",
    "cli",
    "load_manifest",
    "main",
    "parse_args",
    "render_markdown",
    "run_benchmark",
    "summarize_runs",
    "validate_benchmark_cases",
    "compare_reports",
    "render_comparison_markdown",
]


if __name__ == "__main__":
    cli()
