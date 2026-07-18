from pathlib import Path
import json
import os

import pytest

from pyfixagent.agent.default_agent import DefaultAgent
from pyfixagent.main import (
    build_model_extra_body,
    build_system_prompt_as_user,
    load_dotenv_file,
    save_trace,
)
from pyfixagent.models.litellm_model import LiteLLMModel
from pyfixagent.sandbox.factory import build_sandbox
from pyfixagent.utils.config import load_config
from scripts.reset_demo import reset_demo


pytestmark = pytest.mark.integration


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def require_real_model_config():
    root = project_root()
    load_dotenv_file(root / ".env")
    config = load_config(root / "configs" / "default.yaml")

    model_config = config.get("model", {})
    model_name = os.getenv("LITELLM_MODEL_NAME") or model_config.get("name")
    if not model_name:
        pytest.skip("missing LITELLM_MODEL_NAME or model.name in configs/default.yaml")

    provider = model_config.get("provider")
    if os.getenv("LITELLM_MODEL_NAME"):
        litellm_model_name = os.getenv("LITELLM_MODEL_NAME")
    elif provider == "openai_compatible":
        litellm_model_name = f"openai/{model_name}"
    else:
        litellm_model_name = f"{provider}/{model_name}" if provider else model_name

    api_key_env = model_config.get("api_key_env") or "OPENAI_API_KEY"
    api_key = os.getenv(api_key_env)
    if not api_key:
        pytest.skip(f"missing API key environment variable: {api_key_env}")

    api_base = model_config.get("api_base")
    if provider == "openai_compatible" and not api_base:
        pytest.skip("missing api_base for openai_compatible model config")

    return config, LiteLLMModel(
        model_name=litellm_model_name,
        api_base=api_base,
        api_key=api_key,
        temperature=float(model_config.get("temperature", 0.0)),
        max_tokens=int(model_config.get("max_tokens", 2000)),
        timeout_seconds=int(model_config.get("timeout_seconds", 60)),
        extra_body=build_model_extra_body(model_config),
        system_prompt_as_user=build_system_prompt_as_user(model_config),
    )


@pytest.mark.skipif(os.getenv("RUN_LLM_TESTS") != "1", reason="set RUN_LLM_TESTS=1 to run real LLM integration tests")
def test_agent_runs_with_real_model_and_writes_trace():
    root = project_root()
    config, model = require_real_model_config()
    workspace = root / "workspaces" / "demo_project"
    patch_output_dir = root / config["paths"].get("patch_output_dir", "outputs/patches")
    trace_output_dir = root / config["paths"].get("trace_output_dir", "outputs/traces")

    reset_demo(clean_outputs_requested=False)
    try:
        agent = DefaultAgent(
            model=model,
            sandbox=build_sandbox(workspace, config.get("sandbox", {})),
            patch_output_dir=patch_output_dir,
            max_iterations=2,
            isolate_workspace=True,
        )
        result = agent.run(
            "Fix the failing tests in workspaces/demo_project. "
            "Only modify files under src/. Do not modify tests/. Return only a unified diff patch."
        )
        trace_path = save_trace(result, trace_output_dir)

        assert trace_path.exists()
        data = json.loads(trace_path.read_text(encoding="utf-8"))
        assert data["workspace_strategy"] == "temporary_git_worktree"
        assert isinstance(data["iterations"], list)
        assert len(result.iterations) > 0
        assert any(record.raw_model_output for record in result.iterations)
        assert all(record.mode for record in result.iterations)
        assert data["environment"]["execution"]["backend"] == "container"
        assert result.success is True

        assert result.error is None
    finally:
        reset_demo(clean_outputs_requested=False)
