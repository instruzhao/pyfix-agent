import json

from pyfixagent.benchmarking.compare_cli import main as compare_main
from pyfixagent.benchmarking.comparison import compare_reports
from pyfixagent.benchmarking.metrics import wilson_interval
from pyfixagent.benchmarking.provenance import build_protocol_metadata


def _report(successes, *, manifest="same", model="model-a"):
    runs = [
        {
            "case_id": case_id,
            "strategy": "traceback",
            "variant": "repository",
            "repetition": 1,
            "success": success,
            "failure_type": None if success else "holdout_failed",
            "input_tokens": 10,
            "output_tokens": 2,
            "duration_seconds": 1.0,
        }
        for case_id, success in successes
    ]
    return {
        "schema_version": 5,
        "protocol": {
            "manifest_sha256": manifest,
            "case_ids": sorted(case_id for case_id, _ in successes),
            "repeat": 1,
            "strategies": ["traceback"],
            "repository_modes": ["on"],
            "model": model,
        },
        "runs": runs,
    }


def test_wilson_interval_exposes_small_sample_uncertainty():
    assert wilson_interval(0, 0) is None
    assert wilson_interval(24, 24) == [0.862, 1.0]


def test_comparison_uses_only_matched_trials_and_reports_paired_evidence():
    baseline = _report([("a", False), ("b", True), ("baseline-only", True)])
    candidate = _report([("a", True), ("b", False), ("candidate-only", True)])

    result = compare_reports(baseline, candidate)

    assert result["matched_runs"] == 2
    assert result["wins"] == 1
    assert result["losses"] == 1
    assert result["ties"] == 0
    assert result["mcnemar_exact_pvalue"] == 1.0
    assert result["baseline_only_runs"] == 1
    assert result["candidate_only_runs"] == 1
    assert result["comparison_complete"] is False
    assert result["protocol_compatibility"]["compatible"] is False


def test_compare_cli_fails_closed_on_protocol_drift(tmp_path):
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(json.dumps(_report([("a", True)])), encoding="utf-8")
    candidate_path.write_text(
        json.dumps(_report([("a", True)], manifest="different")), encoding="utf-8"
    )

    assert compare_main([str(baseline_path), str(candidate_path)]) == 2
    assert compare_main(
        [
            str(baseline_path),
            str(candidate_path),
            "--allow-protocol-drift",
            "--allow-unmatched",
        ]
    ) == 0


def test_compare_cli_fails_closed_on_unmatched_trials(tmp_path):
    baseline = _report([("a", True), ("b", True)])
    candidate = _report([("a", True), ("b", True)])
    candidate["runs"].pop()
    baseline_path = tmp_path / "baseline.json"
    candidate_path = tmp_path / "candidate.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")
    candidate_path.write_text(json.dumps(candidate), encoding="utf-8")

    assert compare_main([str(baseline_path), str(candidate_path)]) == 3
    assert compare_main(
        [str(baseline_path), str(candidate_path), "--allow-unmatched"]
    ) == 0


def test_comparison_rejects_duplicate_trial_identities():
    baseline = _report([("a", True)])
    baseline["runs"].append(dict(baseline["runs"][0]))

    try:
        compare_reports(baseline, _report([("a", True)]))
    except ValueError as exc:
        assert "duplicate baseline trial identity" in str(exc)
    else:
        raise AssertionError("duplicate trials must not be silently overwritten")


def test_protocol_metadata_hashes_inputs_without_copying_secrets(tmp_path):
    manifest = tmp_path / "cases.yaml"
    config = tmp_path / "config.yaml"
    manifest.write_text("schema_version: 3\n", encoding="utf-8")
    config.write_text("api_key_env: SECRET_NAME\n", encoding="utf-8")

    metadata = build_protocol_metadata(
        project_root=tmp_path,
        manifest_path=manifest,
        config_path=config,
        case_ids=["b", "a"],
        repeat=4,
        strategies=["traceback"],
        repository_modes=["on"],
        trace_redaction="safe",
        model_name="openai/model-a",
        review_model_name="openai/model-b",
        sandbox_backend="container",
        container_engine="podman",
        container_image="runner:test",
    )

    assert metadata["case_ids"] == ["a", "b"]
    assert len(metadata["manifest_sha256"]) == 64
    assert len(metadata["config_sha256"]) == 64
    assert "SECRET_NAME" not in json.dumps(metadata)
    assert metadata["container_engine"] == "podman"
