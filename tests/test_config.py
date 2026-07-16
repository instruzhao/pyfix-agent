from pathlib import Path

from pyfixagent.main import parse_args, resolve_runtime_config


def test_default_config_matches_documented_defaults():
    project_root = Path(__file__).resolve().parents[1]
    runtime = resolve_runtime_config(project_root, parse_args([]))

    assert runtime["initial_mode"] == "replacement"
    assert runtime["context_strategy"] == "traceback"
    assert runtime["max_iterations"] == 5
    assert runtime["context_line_window"] == 25
    assert runtime["context_max_files"] == 6
    assert runtime["context_fallback_to_full"] is True
    assert runtime["context_include_tests"] is True
    assert runtime["isolate_workspace"] is True
    assert runtime["test_commands"] == (("python", "-m", "pytest", "-p", "no:cacheprovider"),)
    assert runtime["config"]["model"]["name"] == "qwen3.6-max-preview"
