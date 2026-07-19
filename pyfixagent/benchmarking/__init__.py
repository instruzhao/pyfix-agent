"""Isolated benchmark protocol, execution, metrics, and reporting."""

from pyfixagent.benchmarking.comparison import compare_reports, render_comparison_markdown
from pyfixagent.benchmarking.contracts import BenchmarkCase, build_generic_task
from pyfixagent.benchmarking.manifest import load_manifest, validate_benchmark_cases
from pyfixagent.benchmarking.metrics import summarize_runs
from pyfixagent.benchmarking.reporting import render_markdown
from pyfixagent.benchmarking.runner import run_benchmark

__all__ = [
    "compare_reports",
    "render_comparison_markdown",
    "BenchmarkCase",
    "build_generic_task",
    "load_manifest",
    "render_markdown",
    "run_benchmark",
    "summarize_runs",
    "validate_benchmark_cases",
]
