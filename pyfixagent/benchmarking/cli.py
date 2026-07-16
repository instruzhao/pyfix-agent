from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pyfixagent.benchmarking.manifest import load_manifest, validate_benchmark_cases
from pyfixagent.benchmarking.paths import resolve
from pyfixagent.benchmarking.reporting import render_markdown
from pyfixagent.benchmarking.runner import run_benchmark
from pyfixagent.main import build_litellm_model_name, load_dotenv_file
from pyfixagent.execution.test_policy import normalize_test_commands
from pyfixagent.models.base import BaseModel
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.utils.config import load_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated PyFixAgent benchmark cases.")
    parser.add_argument("--manifest", default="benchmarks/cases.yaml")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--strategy", action="append", choices=["traceback", "full"], dest="strategies")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output-dir", default="outputs/benchmarks")
    parser.add_argument("--list", action="store_true", dest="list_cases")
    parser.add_argument("--validate", action="store_true", dest="validate_cases")
    parser.add_argument("--keep-workspaces", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    project_root = Path(__file__).resolve().parents[2]
    cases = load_manifest(resolve(project_root, args.manifest), project_root)
    if args.case_ids:
        selected = set(args.case_ids)
        cases = [case for case in cases if case.case_id in selected]
        missing = selected - {case.case_id for case in cases}
        if missing:
            raise ValueError(f"unknown benchmark cases: {', '.join(sorted(missing))}")
    if args.list_cases:
        for case in cases:
            source = case.fixture or case.workspace
            holdout = case.holdout_path or "none"
            print(f"{case.case_id}\t{source}\tholdout={holdout}")
        return 0
    if args.validate_cases:
        results = validate_benchmark_cases(cases)
        for result in results:
            status = "ok" if result["valid"] else "invalid"
            print(f"{result['case_id']}\t{status}\t{result['reason']}")
        return 0 if all(result["valid"] for result in results) else 1

    load_dotenv_file(project_root / ".env")
    config = load_config(resolve(project_root, args.config))
    model_config = config.get("model", {})

    def model_factory() -> BaseModel:
        api_key_env = model_config.get("api_key_env")
        return LiteLLMModel(
            model_name=build_litellm_model_name(model_config),
            api_base=model_config.get("api_base"),
            api_key=os.getenv(api_key_env) if api_key_env else None,
            temperature=float(model_config.get("temperature", 0.0)),
            max_tokens=int(model_config.get("max_tokens", 2000)),
            timeout_seconds=int(model_config.get("timeout_seconds", 60)),
            extra_body={"enable_thinking": bool(model_config.get("enable_thinking", False))},
        )

    output_dir = resolve(project_root, args.output_dir)
    report = run_benchmark(
        cases=cases,
        project_root=project_root,
        output_dir=output_dir,
        model_factory=model_factory,
        repeat=args.repeat,
        strategy_override=tuple(args.strategies or ()),
        keep_workspaces=args.keep_workspaces,
        sandbox_timeout=int(config.get("sandbox", {}).get("timeout_seconds", 30)),
        context_line_window=int(config.get("context", {}).get("line_window", 25)),
        context_max_files=int(config.get("context", {}).get("max_files", 6)),
        max_changed_files=int(config.get("safety", {}).get("max_changed_files", 8)),
        max_changed_lines=int(config.get("safety", {}).get("max_changed_lines", 400)),
        test_commands=normalize_test_commands(config.get("test", {}).get("commands")),
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output_dir / "report.md").write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    return 0 if report["summary"]["success_rate"] == 1.0 else 1


def cli() -> None:
    raise SystemExit(main())
