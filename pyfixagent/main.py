from pathlib import Path
import argparse
from dataclasses import asdict
from datetime import datetime
import json
import os
from pprint import pprint

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.schemas import AgentResult
from pyfixagent.trace import collect_environment, final_summary
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
DEFAULT_CONTEXT_FALLBACK_TO_FULL = True
DEFAULT_CONTEXT_INCLUDE_TESTS = True
DEFAULT_REQUIRE_CLEAN_WORKSPACE = True
DEFAULT_MAX_CHANGED_FILES = 8
DEFAULT_MAX_CHANGED_LINES = 400


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


def save_trace(result: AgentResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    if result.environment is None:
        result.environment = collect_environment(result.workspace)
    if result.final_summary is None:
        result.final_summary = final_summary(result)
    trace_path = output_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}.json"
    trace_path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
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
        "--allowed-path",
        action="append",
        dest="allowed_paths",
        help="Restrict edits to this workspace-relative path. May be specified more than once.",
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
    }


def build_litellm_model_name(model_config: dict) -> str:
    model_name = model_config.get("name", "gpt-4o-mini")
    provider = model_config.get("provider")
    if provider == "openai_compatible":
        return f"openai/{model_name}"
    return f"{provider}/{model_name}" if provider else model_name


def main(argv: list[str] | None = None) -> int:
    project_root = Path(__file__).resolve().parents[1]
    args = parse_args(argv)
    load_dotenv_file(project_root / ".env")
    runtime = resolve_runtime_config(project_root, args)
    config = runtime["config"]

    model_config = config.get("model", {})
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
        extra_body={"enable_thinking": bool(model_config.get("enable_thinking", False))},
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
        context_fallback_to_full=runtime["context_fallback_to_full"],
        context_include_tests=runtime["context_include_tests"],
        require_clean_workspace=runtime["require_clean_workspace"],
        allowed_paths=runtime["allowed_paths"],
        max_changed_files=runtime["max_changed_files"],
        max_changed_lines=runtime["max_changed_lines"],
    )
    result = agent.run(runtime["task"])
    trace_path = save_trace(result, runtime["trace_output_dir"])
    print(f"[agent] trace saved to {trace_path}")
    pprint(result)
    return 0 if result.success else 1


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
