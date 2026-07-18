from pathlib import Path
import argparse
from dataclasses import asdict
from datetime import datetime
import json
import os
from pprint import pprint

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.execution.test_policy import normalize_test_commands
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.schemas import AgentResult
from pyfixagent.trace import collect_environment, final_summary
from pyfixagent.trace_redaction import TRACE_REDACTION_MODES, TraceRedactor
from pyfixagent.utils.config import load_config
from pyfixagent import __version__


DEFAULT_CONFIG_PATH = "configs/default.yaml"
DEFAULT_WORKSPACE = "workspaces/sklearn_iris_tree_project"
DEFAULT_PATCH_OUTPUT_DIR = "outputs/patches"
DEFAULT_TRACE_OUTPUT_DIR = "outputs/traces"
DEFAULT_TASK = "Fix the failing tests in this small Python project."
DEFAULT_INITIAL_MODE = "replacement"
DEFAULT_MAX_ITERATIONS = 5
DEFAULT_CONTEXT_STRATEGY = "traceback"
DEFAULT_CONTEXT_LINE_WINDOW = 40
DEFAULT_CONTEXT_MAX_FILES = 6
DEFAULT_CONTEXT_MAX_SELECTED_TOKENS = 12000
DEFAULT_CONTEXT_MAX_EXPANSION_LEVEL = 2
DEFAULT_CONTEXT_FALLBACK_TO_FULL = True
DEFAULT_CONTEXT_INCLUDE_TESTS = True
DEFAULT_REQUIRE_CLEAN_WORKSPACE = True
DEFAULT_MAX_CHANGED_FILES = 8
DEFAULT_MAX_CHANGED_LINES = 400
DEFAULT_ISOLATE_WORKSPACE = True
DEFAULT_SEMANTIC_REVIEW_ENABLED = True
DEFAULT_SEMANTIC_REVIEW_MAX_REVISIONS = 2
DEFAULT_SEMANTIC_REVIEW_PARSE_RETRIES = 1
DEFAULT_SEMANTIC_REVIEW_MAX_CONTEXT_CHARS = 16000
DEFAULT_SEMANTIC_REVIEW_MAX_FEEDBACK_CHARS = 3000
DEFAULT_SEMANTIC_REVIEW_MAX_RISKS = 3
DEFAULT_SEMANTIC_REVIEW_MAX_CONTRACTS = 3
DEFAULT_SEMANTIC_REVIEW_MAX_OUTPUT_TOKENS = 3072
DEFAULT_TRACE_REDACTION_MODE = "paths"
DEFAULT_REPOSITORY_CONTEXT_ENABLED = True
DEFAULT_REPOSITORY_CACHE_DIR = "outputs/index"
DEFAULT_REPOSITORY_MAX_FILES = 2000
DEFAULT_REPOSITORY_MAX_FILE_BYTES = 1_000_000
DEFAULT_REPOSITORY_MAX_GRAPH_DEPTH = 2
DEFAULT_REPOSITORY_MAX_RELATED_FILES = 6
DEFAULT_REPOSITORY_MAX_SNIPPET_LINES = 200


def load_dotenv_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        os.environ.setdefault(key, value.strip().strip('"').strip("'"))


def save_trace(result: AgentResult, output_dir: Path, redaction_mode: str = "none") -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if result.environment is None:
        result.environment = collect_environment(result.workspace)
    if result.final_summary is None:
        result.final_summary = final_summary(result)
    trace_path = output_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    trace_data = TraceRedactor(redaction_mode).redact(asdict(result), workspace=result.workspace)
    trace_path.write_text(
        json.dumps(trace_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return trace_path


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run PyFixAgent on a configured local Python workspace.")
    parser.add_argument("--version", action="version", version=f"PyFixAgent {__version__}")
    parser.add_argument(
        "--config",
        default=DEFAULT_CONFIG_PATH,
        help=f"Path to a YAML config file. Defaults to {DEFAULT_CONFIG_PATH}.",
    )
    parser.add_argument("--workspace", help="Workspace path to repair, relative to project root or absolute.")
    parser.add_argument("--task", help="Repair task instruction to send to the model.")
    parser.add_argument(
        "--mode",
        choices=["replacement", "patch"],
        help="Initial repair mode. Overrides agent.initial_mode in config.",
    )
    parser.add_argument(
        "--context-strategy",
        choices=["traceback", "full"],
        help="Context selection strategy. Overrides context.strategy in config.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        help="Maximum repair iterations. Overrides agent.max_iterations in config.",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Allow running in a workspace with uncommitted changes. Disabled by default for safety.",
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help="Repair the selected workspace in place instead of using a temporary Git worktree.",
    )
    parser.add_argument(
        "--allowed-path",
        action="append",
        dest="allowed_paths",
        help="Restrict edits to this workspace-relative path. May be specified more than once.",
    )
    review_group = parser.add_mutually_exclusive_group()
    review_group.add_argument(
        "--semantic-review",
        action="store_true",
        dest="semantic_review",
        default=None,
        help="Require semantic acceptance after visible tests pass.",
    )
    review_group.add_argument(
        "--no-semantic-review",
        action="store_false",
        dest="semantic_review",
        help="Use visible pytest success as the final acceptance signal.",
    )
    repository_group = parser.add_mutually_exclusive_group()
    repository_group.add_argument(
        "--repository-context",
        action="store_true",
        dest="repository_context",
        default=None,
        help="Enable static repository indexing and graph-expanded context.",
    )
    repository_group.add_argument(
        "--no-repository-context",
        action="store_false",
        dest="repository_context",
        help="Use only the legacy traceback/full context selector.",
    )
    parser.add_argument(
        "--trace-redaction",
        choices=sorted(TRACE_REDACTION_MODES),
        help="Trace privacy mode: none, paths, or safe source-content redaction.",
    )
    return parser.parse_args(argv)


def resolve_runtime_config(project_root: Path, args: argparse.Namespace) -> dict:
    config_path = _resolve_path(project_root, args.config)
    config = load_config(config_path)
    paths_config = config.get("paths", {})
    agent_config = config.get("agent", {})
    context_config = config.get("context", {})
    sandbox_config = config.get("sandbox", {})
    safety_config = config.get("safety", {})
    test_config = config.get("test", {})
    review_config = config.get("semantic_review", {})
    repository_config = config.get("repository", {})
    trace_config = config.get("trace", {})

    workspace = _resolve_path(project_root, args.workspace or paths_config.get("workspace", DEFAULT_WORKSPACE))
    return {
        "config_path": config_path,
        "config": config,
        "workspace": workspace,
        "patch_output_dir": _resolve_path(
            project_root,
            paths_config.get("patch_output_dir", DEFAULT_PATCH_OUTPUT_DIR),
        ),
        "trace_output_dir": _resolve_path(
            project_root,
            paths_config.get("trace_output_dir", DEFAULT_TRACE_OUTPUT_DIR),
        ),
        "task": args.task or agent_config.get("task", DEFAULT_TASK),
        "initial_mode": args.mode or agent_config.get("initial_mode", DEFAULT_INITIAL_MODE),
        "max_iterations": int(
            args.max_iterations
            if args.max_iterations is not None
            else agent_config.get("max_iterations", DEFAULT_MAX_ITERATIONS)
        ),
        "context_strategy": args.context_strategy or context_config.get("strategy", DEFAULT_CONTEXT_STRATEGY),
        "context_line_window": int(context_config.get("line_window", DEFAULT_CONTEXT_LINE_WINDOW)),
        "context_max_files": int(context_config.get("max_files", DEFAULT_CONTEXT_MAX_FILES)),
        "context_max_selected_tokens": int(
            context_config.get("max_selected_tokens", DEFAULT_CONTEXT_MAX_SELECTED_TOKENS)
        ),
        "context_max_expansion_level": int(
            context_config.get("max_expansion_level", DEFAULT_CONTEXT_MAX_EXPANSION_LEVEL)
        ),
        "context_fallback_to_full": _as_bool(
            context_config.get("fallback_to_full_context", DEFAULT_CONTEXT_FALLBACK_TO_FULL)
        ),
        "context_include_tests": _as_bool(context_config.get("include_tests", DEFAULT_CONTEXT_INCLUDE_TESTS)),
        "sandbox_timeout": int(sandbox_config.get("timeout_seconds", 30)),
        "require_clean_workspace": (
            False
            if getattr(args, "allow_dirty", False)
            else _as_bool(safety_config.get("require_clean_workspace", DEFAULT_REQUIRE_CLEAN_WORKSPACE))
        ),
        "allowed_paths": (
            list(getattr(args, "allowed_paths", None) or safety_config.get("allowed_paths", []) or [])
        ),
        "max_changed_files": int(safety_config.get("max_changed_files", DEFAULT_MAX_CHANGED_FILES)),
        "max_changed_lines": int(safety_config.get("max_changed_lines", DEFAULT_MAX_CHANGED_LINES)),
        "isolate_workspace": (
            False
            if getattr(args, "in_place", False)
            else _as_bool(safety_config.get("isolate_workspace", DEFAULT_ISOLATE_WORKSPACE))
        ),
        "test_commands": normalize_test_commands(test_config.get("commands")),
        "semantic_review_enabled": (
            bool(args.semantic_review)
            if getattr(args, "semantic_review", None) is not None
            else _as_bool(review_config.get("enabled", DEFAULT_SEMANTIC_REVIEW_ENABLED))
        ),
        "semantic_review_max_revisions": int(
            review_config.get("max_semantic_revisions", DEFAULT_SEMANTIC_REVIEW_MAX_REVISIONS)
        ),
        "semantic_review_parse_retries": int(
            review_config.get("max_parse_retries", DEFAULT_SEMANTIC_REVIEW_PARSE_RETRIES)
        ),
        "semantic_review_max_context_chars": int(
            review_config.get("max_context_chars", DEFAULT_SEMANTIC_REVIEW_MAX_CONTEXT_CHARS)
        ),
        "semantic_review_max_feedback_chars": int(
            review_config.get("max_feedback_chars", DEFAULT_SEMANTIC_REVIEW_MAX_FEEDBACK_CHARS)
        ),
        "semantic_review_max_risks": int(
            review_config.get("max_risks", DEFAULT_SEMANTIC_REVIEW_MAX_RISKS)
        ),
        "semantic_review_max_contracts": int(
            review_config.get("max_contracts", DEFAULT_SEMANTIC_REVIEW_MAX_CONTRACTS)
        ),
        "semantic_review_max_output_tokens": int(
            review_config.get("max_output_tokens", DEFAULT_SEMANTIC_REVIEW_MAX_OUTPUT_TOKENS)
        ),
        "semantic_review_thinking_budget": (
            int(review_config["thinking_budget"])
            if review_config.get("thinking_budget") is not None
            else None
        ),
        "repository_context_enabled": (
            bool(args.repository_context)
            if getattr(args, "repository_context", None) is not None
            else _as_bool(repository_config.get("enabled", DEFAULT_REPOSITORY_CONTEXT_ENABLED))
        ),
        "repository_cache_dir": _resolve_path(
            project_root,
            repository_config.get("cache_dir", DEFAULT_REPOSITORY_CACHE_DIR),
        ),
        "repository_max_files": int(
            repository_config.get("max_files", DEFAULT_REPOSITORY_MAX_FILES)
        ),
        "repository_max_file_bytes": int(
            repository_config.get("max_file_bytes", DEFAULT_REPOSITORY_MAX_FILE_BYTES)
        ),
        "repository_max_graph_depth": int(
            repository_config.get("max_graph_depth", DEFAULT_REPOSITORY_MAX_GRAPH_DEPTH)
        ),
        "repository_max_related_files": int(
            repository_config.get("max_related_files", DEFAULT_REPOSITORY_MAX_RELATED_FILES)
        ),
        "repository_max_snippet_lines": int(
            repository_config.get("max_snippet_lines", DEFAULT_REPOSITORY_MAX_SNIPPET_LINES)
        ),
        "trace_redaction_mode": (
            getattr(args, "trace_redaction", None)
            or str(trace_config.get("redaction_mode", DEFAULT_TRACE_REDACTION_MODE)).strip().lower()
        ),
    }


def build_litellm_model_name(model_config: dict) -> str:
    model_name = model_config.get("name", "gpt-4o-mini")
    provider = model_config.get("provider")
    if provider == "openai_compatible":
        return f"openai/{model_name}"
    return f"{provider}/{model_name}" if provider else model_name


def build_model_extra_body(model_config: dict) -> dict:
    extra_body = {"enable_thinking": _as_bool(model_config.get("enable_thinking", False))}
    thinking_budget = model_config.get("thinking_budget")
    if thinking_budget is not None:
        extra_body["thinking_budget"] = max(1, int(thinking_budget))
    return extra_body


def build_system_prompt_as_user(model_config: dict) -> bool:
    return _as_bool(model_config.get("system_prompt_as_user", False))


def build_review_model_config(model_config: dict, review_config: dict) -> dict:
    configured = dict(model_config)
    configured["max_tokens"] = max(
        256,
        int(review_config.get("max_output_tokens", DEFAULT_SEMANTIC_REVIEW_MAX_OUTPUT_TOKENS)),
    )
    configured["enable_thinking"] = _as_bool(
        review_config.get("enable_thinking", model_config.get("enable_thinking", False))
    )
    thinking_budget = review_config.get("thinking_budget")
    if configured["enable_thinking"] and thinking_budget is not None:
        configured["thinking_budget"] = max(1, int(thinking_budget))
    else:
        configured.pop("thinking_budget", None)
    return configured


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[1]
    args = parse_args(argv)
    load_dotenv_file(project_root / ".env")
    runtime = resolve_runtime_config(project_root, args)
    config = runtime["config"]

    model_config = config.get("model", {})
    review_config = config.get("semantic_review", {})
    litellm_model_name = build_litellm_model_name(model_config)

    api_key_env = model_config.get("api_key_env")
    api_key = os.getenv(api_key_env) if api_key_env else None
    model = LiteLLMModel(
        model_name=litellm_model_name,
        api_base=model_config.get("api_base"),
        api_key=api_key,
        temperature=float(model_config.get("temperature", 0.0)),
        max_tokens=int(model_config.get("max_tokens", 2000)),
        timeout_seconds=int(model_config.get("timeout_seconds", 60)),
        extra_body=build_model_extra_body(model_config),
        system_prompt_as_user=build_system_prompt_as_user(model_config),
    )
    review_model_config = build_review_model_config(model_config, review_config)
    review_api_key_env = review_model_config.get("api_key_env")
    review_model = LiteLLMModel(
        model_name=build_litellm_model_name(review_model_config),
        api_base=review_model_config.get("api_base"),
        api_key=os.getenv(review_api_key_env) if review_api_key_env else None,
        temperature=float(review_model_config.get("temperature", 0.0)),
        max_tokens=int(review_model_config.get("max_tokens", DEFAULT_SEMANTIC_REVIEW_MAX_OUTPUT_TOKENS)),
        timeout_seconds=int(review_model_config.get("timeout_seconds", 60)),
        extra_body=build_model_extra_body(review_model_config),
        system_prompt_as_user=build_system_prompt_as_user(review_model_config),
    )

    sandbox = LocalSandbox(
        workspace=runtime["workspace"],
        timeout_seconds=runtime["sandbox_timeout"],
    )

    agent = DefaultAgent(
        model=model,
        sandbox=sandbox,
        patch_output_dir=runtime["patch_output_dir"],
        max_iterations=runtime["max_iterations"],
        initial_mode=runtime["initial_mode"],
        context_strategy=runtime["context_strategy"],
        context_line_window=runtime["context_line_window"],
        context_max_files=runtime["context_max_files"],
        context_max_expansion_level=runtime["context_max_expansion_level"],
        context_fallback_to_full=runtime["context_fallback_to_full"],
        context_include_tests=runtime["context_include_tests"],
        require_clean_workspace=runtime["require_clean_workspace"],
        allowed_paths=runtime["allowed_paths"],
        max_changed_files=runtime["max_changed_files"],
        max_changed_lines=runtime["max_changed_lines"],
        isolate_workspace=runtime["isolate_workspace"],
        test_commands=runtime["test_commands"],
        semantic_review_enabled=runtime["semantic_review_enabled"],
        semantic_review_max_revisions=runtime["semantic_review_max_revisions"],
        semantic_review_parse_retries=runtime["semantic_review_parse_retries"],
        semantic_review_max_context_chars=runtime["semantic_review_max_context_chars"],
        semantic_review_max_feedback_chars=runtime["semantic_review_max_feedback_chars"],
        semantic_review_max_risks=runtime["semantic_review_max_risks"],
        semantic_review_max_contracts=runtime["semantic_review_max_contracts"],
        review_model=review_model,
        repository_context_enabled=runtime["repository_context_enabled"],
        repository_cache_dir=runtime["repository_cache_dir"],
        repository_max_files=runtime["repository_max_files"],
        repository_max_file_bytes=runtime["repository_max_file_bytes"],
        repository_max_graph_depth=runtime["repository_max_graph_depth"],
        repository_max_related_files=runtime["repository_max_related_files"],
        repository_max_snippet_lines=runtime["repository_max_snippet_lines"],
        context_max_selected_tokens=runtime["context_max_selected_tokens"],
    )
    result = agent.run(runtime["task"])
    trace_path = save_trace(
        result,
        runtime["trace_output_dir"],
        redaction_mode=runtime["trace_redaction_mode"],
    )
    print(f"[agent] trace saved to {trace_path}")
    pprint(result)
    if result.success:
        return 0
    if getattr(result, "visible_success", False) and getattr(
        result, "acceptance_status", "not_run"
    ) not in {"disabled", "not_run"}:
        return 2
    return 1


def cli() -> None:
    raise SystemExit(main())


def _resolve_path(project_root: Path, raw_path: str | Path) -> Path:
    path = Path(raw_path)
    return path if path.is_absolute() else project_root / path


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


if __name__ == "__main__":
    cli()
