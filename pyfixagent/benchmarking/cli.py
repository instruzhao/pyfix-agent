from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pyfixagent.benchmarking.manifest import load_manifest, validate_benchmark_cases
from pyfixagent.benchmarking.paths import resolve
from pyfixagent.benchmarking.reporting import render_markdown
from pyfixagent.benchmarking.runner import run_benchmark
from pyfixagent.main import (
    build_litellm_model_name,
    build_model_extra_body,
    build_review_model_config,
    build_system_prompt_as_user,
    load_dotenv_file,
    _as_bool,
)
from pyfixagent.execution.test_policy import normalize_test_commands
from pyfixagent.models.base import BaseModel
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.sandbox.factory import SANDBOX_BACKENDS, build_sandbox
from pyfixagent.utils.config import load_config
from pyfixagent.trace_redaction import TRACE_REDACTION_MODES


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run isolated PyFixAgent benchmark cases.")
    parser.add_argument("--manifest", default="benchmarks/cases.yaml")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--tag", action="append", dest="tags")
    parser.add_argument("--strategy", action="append", choices=["traceback", "full"], dest="strategies")
    parser.add_argument("--repeat", type=int, default=5)
    parser.add_argument("--output-dir", default="outputs/benchmarks")
    parser.add_argument("--list", action="store_true", dest="list_cases")
    parser.add_argument("--validate", action="store_true", dest="validate_cases")
    parser.add_argument(
        "--validation-timeout",
        type=int,
        default=120,
        help="Per-seed fixture validation timeout in seconds.",
    )
    parser.add_argument("--keep-workspaces", action="store_true")
    parser.add_argument(
        "--repository-mode",
        action="append",
        choices=["on", "off"],
        dest="repository_modes",
        help="Run with repository context on or off; specify both for paired A/B runs.",
    )
    parser.add_argument("--trace-redaction", choices=sorted(TRACE_REDACTION_MODES))
    parser.add_argument(
        "--sandbox-backend",
        choices=sorted(SANDBOX_BACKENDS),
        help="Test and holdout execution backend; overrides sandbox.backend.",
    )
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
    if args.tags:
        requested_tags = set(args.tags)
        cases = [case for case in cases if requested_tags.issubset(case.tags)]
        if not cases:
            raise ValueError(f"no benchmark cases match tags: {', '.join(sorted(requested_tags))}")
    if args.list_cases:
        for case in cases:
            source = case.fixture or case.workspace
            holdout = case.holdout_path or "none"
            tags = ",".join(case.tags) or "none"
            print(f"{case.case_id}\t{source}\tholdout={holdout}\ttags={tags}")
        return 0
    if args.validate_cases:
        results = validate_benchmark_cases(cases, timeout=max(1, args.validation_timeout))
        for result in results:
            status = "ok" if result["valid"] else "invalid"
            print(f"{result['case_id']}\t{status}\t{result['reason']}")
        return 0 if all(result["valid"] for result in results) else 1

    load_dotenv_file(project_root / ".env")
    config = load_config(resolve(project_root, args.config))
    model_config = config.get("model", {})
    review_config = config.get("semantic_review", {})
    repository_config = config.get("repository", {})
    context_config = config.get("context", {})
    trace_config = config.get("trace", {})
    sandbox_config = config.get("sandbox", {})

    def model_factory() -> BaseModel:
        api_key_env = model_config.get("api_key_env")
        return LiteLLMModel(
            model_name=build_litellm_model_name(model_config),
            api_base=model_config.get("api_base"),
            api_key=os.getenv(api_key_env) if api_key_env else None,
            temperature=float(model_config.get("temperature", 0.0)),
            max_tokens=int(model_config.get("max_tokens", 2000)),
            timeout_seconds=int(model_config.get("timeout_seconds", 60)),
            extra_body=build_model_extra_body(model_config),
            system_prompt_as_user=build_system_prompt_as_user(model_config),
        )

    review_model_config = build_review_model_config(model_config, review_config)

    def review_model_factory() -> BaseModel:
        api_key_env = review_model_config.get("api_key_env")
        return LiteLLMModel(
            model_name=build_litellm_model_name(review_model_config),
            api_base=review_model_config.get("api_base"),
            api_key=os.getenv(api_key_env) if api_key_env else None,
            temperature=float(review_model_config.get("temperature", 0.0)),
            max_tokens=int(review_model_config.get("max_tokens", 3072)),
            timeout_seconds=int(review_model_config.get("timeout_seconds", 60)),
            extra_body=build_model_extra_body(review_model_config),
            system_prompt_as_user=build_system_prompt_as_user(review_model_config),
        )

    output_dir = resolve(project_root, args.output_dir)

    def sandbox_factory(workspace: Path):
        return build_sandbox(
            workspace,
            sandbox_config,
            backend_override=args.sandbox_backend,
        )

    report = run_benchmark(
        cases=cases,
        project_root=project_root,
        output_dir=output_dir,
        model_factory=model_factory,
        review_model_factory=review_model_factory,
        sandbox_factory=sandbox_factory,
        repeat=args.repeat,
        strategy_override=tuple(args.strategies or ()),
        keep_workspaces=args.keep_workspaces,
        sandbox_timeout=int(sandbox_config.get("timeout_seconds", 30)),
        context_line_window=int(context_config.get("line_window", 25)),
        context_max_files=int(context_config.get("max_files", 6)),
        context_max_expansion_level=int(context_config.get("max_expansion_level", 2)),
        max_changed_files=int(config.get("safety", {}).get("max_changed_files", 8)),
        max_changed_lines=int(config.get("safety", {}).get("max_changed_lines", 400)),
        test_commands=normalize_test_commands(config.get("test", {}).get("commands")),
        semantic_review_enabled=_as_bool(review_config.get("enabled", True)),
        semantic_review_max_revisions=int(review_config.get("max_semantic_revisions", 2)),
        semantic_review_parse_retries=int(review_config.get("max_parse_retries", 1)),
        semantic_review_max_context_chars=int(review_config.get("max_context_chars", 16000)),
        semantic_review_max_feedback_chars=int(review_config.get("max_feedback_chars", 3000)),
        semantic_review_max_risks=int(review_config.get("max_risks", 3)),
        semantic_review_max_contracts=int(review_config.get("max_contracts", 3)),
        repository_context_enabled=_as_bool(repository_config.get("enabled", True)),
        repository_modes=(
            tuple(item == "on" for item in args.repository_modes)
            if args.repository_modes
            else None
        ),
        repository_max_files=int(repository_config.get("max_files", 2000)),
        repository_max_file_bytes=int(repository_config.get("max_file_bytes", 1_000_000)),
        repository_max_graph_depth=int(repository_config.get("max_graph_depth", 2)),
        repository_max_related_files=int(repository_config.get("max_related_files", 6)),
        repository_max_snippet_lines=int(repository_config.get("max_snippet_lines", 200)),
        context_max_selected_tokens=int(context_config.get("max_selected_tokens", 12000)),
        trace_redaction_mode=(
            args.trace_redaction or str(trace_config.get("redaction_mode", "paths"))
        ),
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
