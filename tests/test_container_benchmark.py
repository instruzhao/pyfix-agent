from types import SimpleNamespace

import pyfixagent.container_benchmark as benchmark_module
from pyfixagent.container_benchmark import render_markdown, run_qualification


class FakeSandbox:
    calls = 0

    def __init__(self, workspace, timeout_seconds, policy):
        self.workspace = workspace
        self.policy = policy

    def run(self, command):
        self.__class__.calls += 1
        return SimpleNamespace(
            exit_code=0,
            duration=float(self.calls),
            infrastructure_error=False,
            policy_violation=None,
        )

    def environment_metadata(self):
        return {
            "engine": self.policy.engine,
            "engine_server_version": "5.0",
            "image_requested": self.policy.image,
            "image_resolved": "sha256:test",
        }


def test_runner_qualification_separates_first_and_repeated_timings(monkeypatch, tmp_path):
    FakeSandbox.calls = 0
    monkeypatch.setattr(benchmark_module, "ContainerSandbox", FakeSandbox)

    report = run_qualification(
        engine="podman",
        image="runner:test",
        repeat=3,
        probe_limits=False,
        workspace_parent=tmp_path,
    )

    assert report["summary"]["runs"] == 6
    assert report["summary"]["successful_runs"] == 6
    assert report["summary"]["workloads"]["python_startup"]["first_seconds"] == 1.0
    assert report["summary"]["workloads"]["python_startup"]["repeated_mean_seconds"] == 2.5
    assert report["runtime"]["engine"] == "podman"
    assert "Transient create/delete" not in render_markdown(report)
