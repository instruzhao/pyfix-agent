import argparse
from pathlib import Path
import subprocess

from pyfixagent.main import parse_args, resolve_runtime_config


def test_main_help_displays_cli_options():
    completed = subprocess.run(
        ["python", "-m", "pyfixagent.main", "--help"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

    assert completed.returncode == 0
    assert "--workspace" in completed.stdout
    assert "--mode" in completed.stdout
    assert "--context-strategy" in completed.stdout


def test_cli_arguments_override_config(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        "paths:\n"
        "  workspace: workspaces/sklearn_iris_tree_project\n"
        "  patch_output_dir: outputs/patches\n"
        "  trace_output_dir: outputs/traces\n"
        "agent:\n"
        "  task: Config task\n"
        "  initial_mode: patch\n"
        "  max_iterations: 2\n"
        "context:\n"
        "  strategy: full\n"
        "  line_window: 10\n"
        "  max_files: 2\n",
        encoding="utf-8",
    )
    args = parse_args(
        [
            "--config",
            str(config_path),
            "--workspace",
            "workspaces/demo_project",
            "--task",
            "CLI task",
            "--mode",
            "replacement",
            "--context-strategy",
            "traceback",
            "--max-iterations",
            "3",
        ]
    )

    runtime = resolve_runtime_config(tmp_path, args)

    assert runtime["workspace"] == tmp_path / "workspaces/demo_project"
    assert runtime["task"] == "CLI task"
    assert runtime["initial_mode"] == "replacement"
    assert runtime["context_strategy"] == "traceback"
    assert runtime["max_iterations"] == 3
    assert runtime["context_line_window"] == 10


def test_missing_config_fields_use_code_defaults(tmp_path):
    config_path = tmp_path / "minimal.yaml"
    config_path.write_text("model: {}\n", encoding="utf-8")
    args = argparse.Namespace(
        config=str(config_path),
        workspace=None,
        task=None,
        mode=None,
        context_strategy=None,
        max_iterations=None,
    )

    runtime = resolve_runtime_config(tmp_path, args)

    assert runtime["workspace"] == tmp_path / "workspaces/sklearn_iris_tree_project"
    assert runtime["initial_mode"] == "replacement"
    assert runtime["context_strategy"] == "traceback"
    assert runtime["max_iterations"] == 5
