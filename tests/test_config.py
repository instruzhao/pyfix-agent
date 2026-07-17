from pathlib import Path

from pyfixagent.main import (
    build_model_extra_body,
    build_review_model_config,
    build_system_prompt_as_user,
    parse_args,
    resolve_runtime_config,
)


def test_default_config_matches_documented_defaults():
    project_root = Path(__file__).resolve().parents[1]
    runtime = resolve_runtime_config(project_root, parse_args([]))

    assert runtime["initial_mode"] == "replacement"
    assert runtime["context_strategy"] == "traceback"
    assert runtime["max_iterations"] == 5
    assert runtime["context_line_window"] == 25
    assert runtime["context_max_files"] == 6
    assert runtime["context_max_selected_tokens"] == 12000
    assert runtime["context_max_expansion_level"] == 2
    assert runtime["context_fallback_to_full"] is True
    assert runtime["context_include_tests"] is True
    assert runtime["isolate_workspace"] is True
    assert runtime["test_commands"] == (("python", "-m", "pytest", "-p", "no:cacheprovider"),)
    assert runtime["config"]["model"]["name"] == "qwen3.6-max-preview"
    assert build_model_extra_body(runtime["config"]["model"]) == {
        "enable_thinking": True,
        "thinking_budget": 4096,
    }
    assert runtime["config"]["model"]["system_prompt_as_user"] is True
    assert runtime["semantic_review_enabled"] is True
    assert runtime["semantic_review_max_revisions"] == 2
    assert runtime["semantic_review_max_output_tokens"] == 3072
    assert runtime["semantic_review_thinking_budget"] == 1024
    assert runtime["semantic_review_max_contracts"] == 3
    assert runtime["semantic_review_max_risks"] == 3
    assert runtime["trace_redaction_mode"] == "paths"
    assert runtime["repository_context_enabled"] is True
    assert runtime["repository_max_graph_depth"] == 2
    assert runtime["repository_max_related_files"] == 6


def test_cli_can_disable_semantic_review():
    project_root = Path(__file__).resolve().parents[1]
    runtime = resolve_runtime_config(project_root, parse_args(["--no-semantic-review"]))

    assert runtime["semantic_review_enabled"] is False


def test_cli_can_disable_repository_context():
    project_root = Path(__file__).resolve().parents[1]
    runtime = resolve_runtime_config(project_root, parse_args(["--no-repository-context"]))

    assert runtime["repository_context_enabled"] is False


def test_system_prompt_message_mode_parses_string_booleans():
    assert build_system_prompt_as_user({"system_prompt_as_user": "true"}) is True
    assert build_system_prompt_as_user({"system_prompt_as_user": "false"}) is False


def test_review_model_config_has_an_independent_output_and_thinking_budget():
    repair = {
        "name": "qwen",
        "max_tokens": 8192,
        "enable_thinking": True,
        "thinking_budget": 4096,
    }

    review = build_review_model_config(
        repair,
        {"max_output_tokens": 2048, "thinking_budget": 512},
    )

    assert repair["max_tokens"] == 8192
    assert review["max_tokens"] == 2048
    assert review["thinking_budget"] == 512
