from pathlib import Path
from dataclasses import asdict
from datetime import datetime
import json
import os
from pprint import pprint

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.sandbox.local_sandbox import LocalSandbox
from pyfixagent.schemas import AgentResult
from pyfixagent.utils.config import load_config


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
    trace_path = output_dir / f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    trace_path.write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    return trace_path


def main() -> None:
    project_root = Path(__file__).resolve().parents[1]
    load_dotenv_file(project_root / ".env")
    config = load_config(project_root / "configs" / "default.yaml")

    workspace = project_root / config["paths"]["workspace"]
    patch_output_dir = project_root / config["paths"]["patch_output_dir"]
    trace_output_dir = project_root / config["paths"].get("trace_output_dir", "outputs/traces")

    model_config = config.get("model", {})
    model_name = model_config.get("name", "gpt-4o-mini")
    provider = model_config.get("provider")
    if provider == "openai_compatible":
        litellm_model_name = f"openai/{model_name}"
    else:
        litellm_model_name = f"{provider}/{model_name}" if provider else model_name

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

    sandbox_config = config.get("sandbox", {})
    sandbox = LocalSandbox(
        workspace=workspace,
        timeout_seconds=int(sandbox_config.get("timeout_seconds", 30)),
    )

    agent_config = config.get("agent", {})
    agent = DefaultAgent(
        model=model,
        sandbox=sandbox,
        patch_output_dir=patch_output_dir,
        max_iterations=int(agent_config.get("max_iterations", 1)),
    )
    task = agent_config.get(
        "task",
        "Fix the failing tests in this small Python project.",
    )
    result = agent.run(task)
    trace_path = save_trace(result, trace_output_dir)
    print(f"[agent] trace saved to {trace_path}")
    pprint(result)


if __name__ == "__main__":
    main()
