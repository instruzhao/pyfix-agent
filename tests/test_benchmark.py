import json
from pathlib import Path
import subprocess

import pytest
import pyfixagent.benchmarking.manifest as manifest_module

from pyfixagent.benchmark import (
    BenchmarkCase,
    build_generic_task,
    load_manifest,
    parse_args,
    render_markdown,
    run_benchmark,
    summarize_runs,
    validate_benchmark_cases,
)
from pyfixagent.models.mock_model import MockModel
from pyfixagent.benchmarking.runner import _apply_exported_patch


def test_load_manifest_validates_and_resolves_cases(tmp_path):
    workspace = tmp_path / "case"
    workspace.mkdir()
    manifest = tmp_path / "cases.yaml"
    manifest.write_text(
        "schema_version: 1\n"
        "cases:\n"
        "  - id: simple\n"
        "    workspace: case\n"
        "    reset_command: [python, reset.py]\n"
        "    allowed_paths: [src]\n"
        "    strategies: [traceback, full]\n",
        encoding="utf-8",
    )

    cases = load_manifest(manifest, tmp_path)

    assert len(cases) == 1
    assert cases[0].case_id == "simple"
    assert cases[0].workspace == workspace
    assert cases[0].allowed_paths == ("src",)
    assert cases[0].strategies == ("traceback", "full")


def test_benchmark_summary_calculates_success_at_one_and_pass_at_k():
    runs = [
        {"case_id": "a", "strategy": "traceback", "repetition": 1, "success": False, "iterations": 2},
        {"case_id": "a", "strategy": "traceback", "repetition": 2, "success": True, "iterations": 1},
        {"case_id": "b", "strategy": "traceback", "repetition": 1, "success": True, "iterations": 1},
    ]

    summary = summarize_runs(runs)

    assert summary["success_rate"] == 0.6667
    assert summary["success_at_1"] == 0.5
    assert summary["pass_at_k"] == 1.0
    assert summary["average_iterations"] == 1.333


def test_render_markdown_contains_run_table():
    runs = [{
        "case_id": "a", "strategy": "traceback", "repetition": 1, "success": True,
        "visible_success": True, "holdout_success": True,
        "iterations": 1, "failure_type": "success", "prompt_chars": 10,
        "input_tokens": 4, "output_tokens": 2,
        "repair_input_tokens": 4, "repair_output_tokens": 2,
    }]
    report = {"summary": summarize_runs(runs), "runs": runs}

    rendered = render_markdown(report)

    assert "Success@1: 100.0%" in rendered
    assert "| a | default | traceback | 1 | yes | n/a | yes | yes |" in rendered


def test_run_benchmark_resets_case_and_saves_trace(tmp_path):
    workspace = tmp_path / "case"
    workspace.mkdir()
    source = workspace / "calculator.py"
    source.write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (workspace / "test_calculator.py").write_text(
        "from calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace, check=True, capture_output=True)
    case = BenchmarkCase(
        case_id="add",
        workspace=workspace,
        task="Fix tests.",
        reset_command=("git", "-C", str(workspace), "restore", "--source", "HEAD", "--", "."),
        allowed_paths=(),
        max_iterations=1,
    )
    replacement = (
        '[{"path":"calculator.py","old":"return a - b","new":"return a + b"}]'
    )

    report = run_benchmark(
        cases=[case],
        project_root=tmp_path,
        output_dir=tmp_path / "outputs",
        model_factory=lambda: MockModel([replacement]),
        repeat=1,
    )

    assert report["summary"]["success_rate"] == 1.0
    assert report["runs"][0]["failure_type"] == "success"
    assert report["runs"][0]["trace_path"]
    assert source.read_text(encoding="utf-8") == "def add(a, b):\n    return a - b\n"


def test_runner_emits_paired_repository_variants_and_schema_four_metrics(tmp_path):
    fixture = tmp_path / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "tests").mkdir()
    (fixture / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8"
    )
    (fixture / "tests" / "test_visible.py").write_text(
        "from src.calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    holdout = tmp_path / "holdout"
    holdout.mkdir()
    (holdout / "test_holdout.py").write_text(
        "from src.calculator import add\n\ndef test_add_negative():\n    assert add(-1, 1) == 0\n",
        encoding="utf-8",
    )
    case = BenchmarkCase(
        case_id="paired",
        allowed_paths=("src",),
        fixture=fixture,
        holdout_path=holdout,
        max_iterations=1,
        context_required_paths=("src/calculator.py",),
        context_relevant_paths=("src/calculator.py", "tests/test_visible.py"),
    )
    replacement = '[{"path":"src/calculator.py","old":"return a - b","new":"return a + b"}]'

    report = run_benchmark(
        cases=[case],
        project_root=tmp_path,
        output_dir=tmp_path / "outputs",
        model_factory=lambda: MockModel([replacement]),
        repeat=1,
        repository_modes=(False, True),
    )

    assert report["schema_version"] == 4
    assert [run["variant"] for run in report["runs"]] == ["legacy", "repository"]
    assert all(run["context_required_recall"] == 1.0 for run in report["runs"])
    assert report["summary"]["repository_ab_pair_count"] == 1
    assert report["summary"]["repository_ab_tie_count"] == 1


def test_v2_manifest_builds_generic_task_and_rejects_task_hints(tmp_path):
    fixture = tmp_path / "fixture"
    holdout = tmp_path / "holdout"
    fixture.mkdir()
    holdout.mkdir()
    manifest = tmp_path / "cases.yaml"
    manifest.write_text(
        "schema_version: 2\n"
        "cases:\n"
        "  - id: simple\n"
        "    fixture: fixture\n"
        "    holdout: holdout\n"
        "    allowed_paths: [src]\n",
        encoding="utf-8",
    )

    case = load_manifest(manifest, tmp_path)[0]

    assert case.fixture == fixture
    assert case.holdout_path == holdout
    assert case.agent_task == "Fix all failing tests. Only modify Python files under src/. Do not modify tests/."
    assert "round" not in case.agent_task.lower()

    manifest.write_text(manifest.read_text(encoding="utf-8") + "    task: Fix rounding\n", encoding="utf-8")
    with pytest.raises(ValueError, match="must not contain task hints"):
        load_manifest(manifest, tmp_path)


def test_v3_manifest_loads_tags_and_context_ground_truth(tmp_path):
    fixture = tmp_path / "fixture"
    holdout = tmp_path / "holdout"
    (fixture / "src").mkdir(parents=True)
    (fixture / "tests").mkdir()
    holdout.mkdir()
    (fixture / "src" / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    (fixture / "src" / "unused.py").write_text("VALUE = 0\n", encoding="utf-8")
    (fixture / "tests" / "test_visible.py").write_text("assert False\n", encoding="utf-8")
    manifest = tmp_path / "cases.yaml"
    manifest.write_text(
        "schema_version: 3\n"
        "cases:\n"
        "  - id: graph\n"
        "    fixture: fixture\n"
        "    holdout: holdout\n"
        "    allowed_paths: [src]\n"
        "    tags: [multifile]\n"
        "    context_required_paths: [src/app.py]\n"
        "    context_relevant_paths: [src/app.py, tests/test_visible.py]\n"
        "    context_distractor_paths: [src/unused.py]\n",
        encoding="utf-8",
    )

    case = load_manifest(manifest, tmp_path)[0]

    assert case.tags == ("multifile",)
    assert case.context_required_paths == ("src/app.py",)
    assert case.context_distractor_paths == ("src/unused.py",)

    manifest.write_text(
        manifest.read_text(encoding="utf-8").replace(
            "context_required_paths: [src/app.py]",
            "context_required_paths: [/src/app.py]",
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="workspace-relative paths"):
        load_manifest(manifest, tmp_path)


def test_summary_separates_repository_ab_and_model_costs():
    runs = [
        {
            "case_id": "a", "strategy": "traceback", "variant": "legacy", "repetition": 1,
            "repository_context_enabled": False, "success": False, "iterations": 1,
            "repair_input_tokens": 10, "repair_output_tokens": 5,
        },
        {
            "case_id": "a", "strategy": "traceback", "variant": "repository", "repetition": 1,
            "repository_context_enabled": True, "success": True, "iterations": 1,
            "repair_input_tokens": 12, "repair_output_tokens": 5,
            "review_input_tokens": 4, "review_output_tokens": 2,
            "context_required_recall": 1.0, "context_precision": 0.75,
            "context_distractor_rate": 0.0,
        },
    ]

    summary = summarize_runs(runs)

    assert summary["repository_success_rate"] == 1.0
    assert summary["legacy_success_rate"] == 0.0
    assert summary["repository_ab_pair_count"] == 1
    assert summary["repository_ab_win_count"] == 1
    assert summary["repair_input_tokens"] == 22
    assert summary["review_input_tokens"] == 4
    assert summary["average_context_required_recall"] == 1.0


def test_summary_marks_an_unobserved_variant_as_not_applicable():
    runs = [
        {
            "case_id": "a",
            "strategy": "traceback",
            "variant": "repository",
            "repetition": 1,
            "repository_context_enabled": True,
            "success": True,
            "iterations": 1,
        }
    ]

    summary = summarize_runs(runs)
    markdown = render_markdown({"summary": summary, "runs": runs})

    assert summary["repository_success_rate"] == 1.0
    assert summary["legacy_success_rate"] is None
    assert "Legacy success rate: n/a" in markdown


def test_fixture_run_uses_external_holdout_as_final_gate(tmp_path):
    fixture = tmp_path / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "tests").mkdir()
    (fixture / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8"
    )
    (fixture / "tests" / "test_visible.py").write_text(
        "from src.calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    holdout = tmp_path / "holdout"
    holdout.mkdir()
    (holdout / "test_holdout.py").write_text(
        "from src.calculator import add\n\ndef test_hidden():\n    assert add(-1, 1) == 99\n",
        encoding="utf-8",
    )
    case = BenchmarkCase(
        case_id="add",
        allowed_paths=("src",),
        fixture=fixture,
        holdout_path=holdout,
        max_iterations=1,
    )
    replacement = '[{"path":"src/calculator.py","old":"return a - b","new":"return a + b"}]'

    report = run_benchmark(
        cases=[case],
        project_root=tmp_path,
        output_dir=tmp_path / "outputs",
        model_factory=lambda: MockModel([replacement]),
        repeat=1,
    )

    run = report["runs"][0]
    assert run["visible_success"] is True
    assert run["holdout_success"] is False
    assert run["success"] is False
    assert run["failure_type"] == "holdout_failed", run
    assert report["summary"]["visible_success_rate"] == 1.0
    assert report["summary"]["success_rate"] == 0.0
    trace = json.loads(Path(run["trace_path"]).read_text(encoding="utf-8"))
    assert "test_hidden" not in trace["iterations"][0]["prompt"]
    assert str(holdout) not in trace["iterations"][0]["prompt"]


def test_cli_defaults_to_five_independent_repetitions():
    assert parse_args([]).repeat == 5
    assert parse_args([]).validation_timeout == 120
    assert "Only modify Python files" in build_generic_task(("src",))
    args = parse_args(["--tag", "multifile", "--repository-mode", "off", "--repository-mode", "on"])
    assert args.tags == ["multifile"]
    assert args.repository_modes == ["off", "on"]


def test_case_validation_requires_failing_visible_baseline_and_external_holdout(tmp_path):
    fixture = tmp_path / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "tests").mkdir()
    (fixture / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    (fixture / "tests" / "test_visible.py").write_text(
        "from src.app import value\n\ndef test_value():\n    assert value == 2\n",
        encoding="utf-8",
    )
    holdout = tmp_path / "holdout"
    holdout.mkdir()
    (holdout / "test_holdout.py").write_text("def test_hidden():\n    assert True\n", encoding="utf-8")
    case = BenchmarkCase(
        case_id="valid",
        allowed_paths=("src",),
        fixture=fixture,
        holdout_path=holdout,
    )

    result = validate_benchmark_cases([case])[0]

    assert result["valid"] is True


def test_case_validation_reports_timeout_instead_of_crashing(monkeypatch, tmp_path):
    fixture = tmp_path / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "tests").mkdir()
    (fixture / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    (fixture / "tests" / "test_visible.py").write_text("def test_value():\n    assert False\n", encoding="utf-8")
    holdout = tmp_path / "holdout"
    holdout.mkdir()
    (holdout / "test_holdout.py").write_text("def test_hidden():\n    assert True\n", encoding="utf-8")
    case = BenchmarkCase(case_id="slow", allowed_paths=("src",), fixture=fixture, holdout_path=holdout)

    def time_out(command, **kwargs):
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(manifest_module.subprocess, "run", time_out)

    result = validate_benchmark_cases([case], timeout=1)[0]

    assert result["valid"] is False
    assert "timed out after 1s" in result["reason"]


def test_fixture_copy_ignores_python_bytecode(tmp_path):
    fixture = tmp_path / "fixture"
    (fixture / "src" / "__pycache__").mkdir(parents=True)
    (fixture / "tests").mkdir()
    (fixture / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    (fixture / "src" / "__pycache__" / "app.pyc").write_bytes(b"bytecode")
    (fixture / "tests" / "test_visible.py").write_text("def test_value():\n    assert False\n", encoding="utf-8")
    case = BenchmarkCase(case_id="clean-copy", allowed_paths=("src",), fixture=fixture)
    from pyfixagent.benchmarking.workspace import IsolatedWorkspaceFactory

    factory = IsolatedWorkspaceFactory(tmp_path, tmp_path / "outputs")
    workspace = factory.prepare(case, "traceback", 1)

    assert not (workspace / "src" / "__pycache__").exists()
    assert factory.cleanup(case, workspace) is None


def test_exported_patch_is_materialized_without_text_newline_translation(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    source = workspace / "app.py"
    source.write_bytes(b"value = 1\n")
    subprocess.run(["git", "init"], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "tests@example.com"], cwd=workspace, check=True)
    subprocess.run(["git", "config", "user.name", "Tests"], cwd=workspace, check=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "baseline"], cwd=workspace, check=True, capture_output=True)
    patch = (
        "diff --git a/app.py b/app.py\n"
        "--- a/app.py\n"
        "+++ b/app.py\n"
        "@@ -1 +1 @@\n"
        "-value = 1\n"
        "+value = 2\n"
    )

    _apply_exported_patch(workspace, patch)

    assert source.read_text(encoding="utf-8") == "value = 2\n"


def test_semantic_rejection_is_still_evaluated_by_external_holdout(tmp_path):
    fixture = tmp_path / "fixture"
    (fixture / "src").mkdir(parents=True)
    (fixture / "tests").mkdir()
    (fixture / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n", encoding="utf-8"
    )
    (fixture / "tests" / "test_visible.py").write_text(
        "from src.calculator import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    holdout = tmp_path / "holdout"
    holdout.mkdir()
    (holdout / "test_holdout.py").write_text(
        "from src.calculator import add\n\ndef test_hidden():\n    assert add(-1, 1) == 0\n",
        encoding="utf-8",
    )
    case = BenchmarkCase(
        case_id="add-review",
        allowed_paths=("src",),
        fixture=fixture,
        holdout_path=holdout,
        max_iterations=1,
    )
    repair = '[{"path":"src/calculator.py","old":"return a - b","new":"return a + b"}]'
    abstain = json.dumps(
        {
            "verdict": "abstain",
            "summary": "Insufficient evidence.",
            "contracts": [],
            "risks": [],
            "repair_feedback": "",
        }
    )

    report = run_benchmark(
        cases=[case],
        project_root=tmp_path,
        output_dir=tmp_path / "outputs",
        model_factory=lambda: MockModel([repair, abstain]),
        repeat=1,
        semantic_review_enabled=True,
        semantic_review_parse_retries=0,
    )

    run = report["runs"][0]
    assert run["visible_success"] is True
    assert run["agent_accepted"] is False
    assert run["holdout_success"] is True
    assert run["candidate_success"] is True
    assert run["success"] is False
    assert run["failure_type"] == "false_reject"
    assert report["summary"]["false_reject_count"] == 1
