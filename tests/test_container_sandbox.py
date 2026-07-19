import os
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

import pyfixagent.sandbox.container_sandbox as container_module
from pyfixagent.sandbox.bounded_process import BoundedProcessResult
from pyfixagent.sandbox.container_sandbox import ContainerPolicy, ContainerSandbox
from pyfixagent.sandbox.factory import build_sandbox


def test_container_policy_rejects_unsafe_or_unbounded_settings():
    with pytest.raises(ValueError, match="image"):
        ContainerPolicy(image="--privileged")
    with pytest.raises(ValueError, match="cpus"):
        ContainerPolicy(cpus=0)
    with pytest.raises(ValueError, match="non-root"):
        ContainerPolicy(user="0:0")
    with pytest.raises(ValueError, match="image_only"):
        ContainerPolicy(dependency_policy="runtime_install")


def test_container_sandbox_builds_hardened_argv_without_a_shell(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "29.0.0\n", "")

    def fake_bounded(command, **kwargs):
        calls.append(command)
        return BoundedProcessResult(0, "1 passed\n", "")

    monkeypatch.setattr(container_module.shutil, "which", lambda engine: f"/bin/{engine}")
    monkeypatch.setattr(container_module.subprocess, "run", fake_run)
    monkeypatch.setattr(container_module, "run_bounded_process", fake_bounded)
    sandbox = ContainerSandbox(
        tmp_path,
        policy=ContainerPolicy(user="65534:65534"),
    )

    result = sandbox.run(["python.exe", "-m", "pytest", "-q"])

    assert result.exit_code == 0
    assert result.backend == "container"
    assert calls[0][1] == "version"
    runtime = calls[1]
    assert runtime[:2] == ["docker", "run"]
    assert "--network" in runtime and runtime[runtime.index("--network") + 1] == "none"
    assert "--ipc" in runtime and runtime[runtime.index("--ipc") + 1] == "none"
    assert "--init" in runtime
    assert "--read-only" in runtime
    assert "--cap-drop" in runtime and runtime[runtime.index("--cap-drop") + 1] == "ALL"
    assert "no-new-privileges:true" in runtime
    assert runtime[runtime.index("--pids-limit") + 1] == "128"
    assert runtime[runtime.index("--memory") + 1] == "1g"
    assert runtime[runtime.index("--user") + 1] == "65534:65534"
    assert "core=0:0" in runtime
    assert "fsize=67108864:67108864" in runtime
    assert "nofile=1024:1024" in runtime
    assert runtime[-4:] == ["python", "-m", "pytest", "-q"]
    mount = runtime[runtime.index("--mount") + 1]
    assert str(tmp_path.resolve()) in mount
    assert result.runtime_command == runtime


def test_container_timeout_forces_named_container_cleanup(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        if command[1] == "version":
            return subprocess.CompletedProcess(command, 0, "29.0.0\n", "")
        return subprocess.CompletedProcess(command, 0, "", "")

    def fake_bounded(command, **kwargs):
        calls.append(command)
        kwargs["terminate"]()
        return BoundedProcessResult(124, "partial", "", timed_out=True)

    monkeypatch.setattr(container_module.shutil, "which", lambda engine: f"/bin/{engine}")
    monkeypatch.setattr(container_module.subprocess, "run", fake_run)
    monkeypatch.setattr(container_module, "run_bounded_process", fake_bounded)
    sandbox = ContainerSandbox(tmp_path, timeout_seconds=1)

    result = sandbox.run(["python", "-m", "pytest"])

    assert result.exit_code == 124
    assert result.timeout is True
    assert calls[0][1] == "version"
    container_name = calls[1][calls[1].index("--name") + 1]
    assert calls[2] == ["docker", "rm", "--force", container_name]


def test_container_output_limit_is_an_infrastructure_policy_error(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "29.0.0\n", "")

    def fake_bounded(command, **kwargs):
        return BoundedProcessResult(
            125,
            "x" * 1024,
            "",
            output_truncated=True,
            policy_violation="combined stdout/stderr exceeded 1024 bytes",
        )

    monkeypatch.setattr(container_module.shutil, "which", lambda engine: f"/bin/{engine}")
    monkeypatch.setattr(container_module.subprocess, "run", fake_run)
    monkeypatch.setattr(container_module, "run_bounded_process", fake_bounded)

    result = ContainerSandbox(tmp_path).run(["python", "-m", "pytest"])

    assert result.infrastructure_error is True
    assert result.output_truncated is True
    assert result.policy_violation is not None
    assert "sandbox policy violation" in result.stderr


def test_container_final_workspace_check_catches_fast_writes(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        return subprocess.CompletedProcess(command, 0, "29.0.0\n", "")

    def fake_bounded(command, **kwargs):
        (tmp_path / "fast-write.bin").write_bytes(b"x" * 32768)
        return BoundedProcessResult(0, "", "")

    monkeypatch.setattr(container_module.shutil, "which", lambda engine: f"/bin/{engine}")
    monkeypatch.setattr(container_module.subprocess, "run", fake_run)
    monkeypatch.setattr(container_module, "run_bounded_process", fake_bounded)

    result = ContainerSandbox(
        tmp_path,
        policy=ContainerPolicy(
            user="65534:65534",
            workspace_write_limit="8k",
        ),
    ).run(["python", "-c", "print('done')"])

    assert result.exit_code == 125
    assert result.infrastructure_error is True
    assert result.policy_violation == "workspace growth exceeded 8192 bytes"


def test_container_daemon_preflight_failure_is_an_infrastructure_error(monkeypatch, tmp_path):
    calls: list[list[str]] = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 1, "", "daemon unavailable")

    monkeypatch.setattr(container_module.shutil, "which", lambda engine: f"/bin/{engine}")
    monkeypatch.setattr(container_module.subprocess, "run", fake_run)

    sandbox = ContainerSandbox(tmp_path)
    result = sandbox.run(["python", "-m", "pytest"])

    assert result.exit_code == 125
    assert result.infrastructure_error is True
    assert "daemon unavailable" in result.stderr
    assert len(calls) == 1
    assert calls[0][1] == "version"
    assert sandbox.environment_metadata()["engine_available"] is False
    assert len(calls) == 1


def test_container_environment_captures_resolved_image_and_policy(monkeypatch, tmp_path):
    def fake_run(command, **kwargs):
        if command[1] == "version":
            return subprocess.CompletedProcess(command, 0, "29.0.0\n", "")
        payload = '{"Id":"sha256:abc","RepoDigests":["runner@sha256:def"]}'
        return subprocess.CompletedProcess(command, 0, payload, "")

    monkeypatch.setattr(container_module.shutil, "which", lambda engine: f"/bin/{engine}")
    monkeypatch.setattr(container_module.subprocess, "run", fake_run)

    metadata = ContainerSandbox(tmp_path).environment_metadata()

    assert metadata["backend"] == "container"
    assert metadata["image_resolved"] == "runner@sha256:def"
    assert metadata["engine_server_version"] == "29.0.0"
    assert metadata["policy"]["network"] == "none"
    assert metadata["policy"]["dependency_policy"] == "image_only"


def test_container_workspace_rebinding_preserves_policy(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    sandbox = ContainerSandbox(tmp_path, timeout_seconds=17, policy=ContainerPolicy(cpus=0.5))

    rebound = sandbox.with_workspace(other)

    assert isinstance(rebound, ContainerSandbox)
    assert rebound.workspace == other
    assert rebound.timeout_seconds == 17
    assert rebound.policy is sandbox.policy
    assert rebound.pytest_basetemp(tmp_path, 2) == "/tmp/pyfixagent-pytest-2"


def test_container_workspace_owner_maps_to_bind_mount_owner(tmp_path):
    resolved = container_module._resolve_runtime_user("workspace_owner", tmp_path)

    if os.name == "posix":
        workspace_stat = tmp_path.stat()
        assert resolved == f"{workspace_stat.st_uid}:{workspace_stat.st_gid}"
    else:
        assert resolved == "65534:65534"


@pytest.mark.skipif(os.name != "posix", reason="POSIX ownership mapping only")
def test_container_workspace_owner_rejects_root_identity():
    workspace = SimpleNamespace(stat=lambda: SimpleNamespace(st_uid=0, st_gid=0))

    with pytest.raises(ValueError, match="resolves to root"):
        container_module._resolve_runtime_user("workspace_owner", workspace)


def test_runner_recipe_is_digest_pinned_hashed_and_non_root():
    root = Path(__file__).resolve().parents[1]
    dockerfile = (root / "containers" / "Dockerfile").read_text(encoding="utf-8")
    lock_lines = [
        line.strip()
        for line in (root / "containers" / "requirements.lock").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]

    assert dockerfile.splitlines()[0].startswith("FROM python:3.12-slim@sha256:")
    assert "--require-hashes" in dockerfile
    assert "USER 65534:65534" in dockerfile
    assert len(lock_lines) == 20
    assert all(" --hash=sha256:" in line for line in lock_lines)


def test_container_blocks_runtime_dependency_install_even_through_python(tmp_path):
    result = ContainerSandbox(tmp_path).run(["python", "-m", "pip", "install", "anything"])

    assert result.exit_code == 126
    assert "image_only" in result.stderr


def test_sandbox_factory_supports_local_and_container(tmp_path):
    local = build_sandbox(tmp_path, {"backend": "local", "timeout_seconds": 9})
    container = build_sandbox(
        tmp_path,
        {
            "backend": "container",
            "timeout_seconds": 11,
            "container": {
                "image": "custom/runner:1",
                "cpus": 0.75,
                "output_limit": "2m",
            },
        },
    )

    assert local.backend == "local"
    assert local.timeout_seconds == 9
    assert isinstance(container, ContainerSandbox)
    assert container.timeout_seconds == 11
    assert container.policy.image == "custom/runner:1"
    assert container.policy.cpus == 0.75
    assert container.policy.output_limit == "2m"
    assert container.policy.user == "workspace_owner"


@pytest.mark.integration
@pytest.mark.skipif(
    __import__("os").environ.get("RUN_DOCKER_TESTS") != "1",
    reason="set RUN_DOCKER_TESTS=1 with the v0.7.1 runner image available",
)
def test_container_sandbox_real_smoke(tmp_path):
    (tmp_path / "test_ok.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    result = ContainerSandbox(tmp_path, timeout_seconds=30).run(
        ["python", "-m", "pytest", "-q", "-p", "no:cacheprovider"]
    )

    assert result.exit_code == 0, result.stderr
    assert "1 passed" in result.stdout


@pytest.mark.integration
@pytest.mark.skipif(
    __import__("os").environ.get("RUN_DOCKER_TESTS") != "1",
    reason="set RUN_DOCKER_TESTS=1 with the v0.7.1 runner image available",
)
def test_container_sandbox_real_output_limit(tmp_path):
    sandbox = ContainerSandbox(
        tmp_path,
        timeout_seconds=30,
        policy=ContainerPolicy(output_limit="8k"),
    )

    result = sandbox.run(["python", "-c", "print('x' * 32768)"])

    assert result.exit_code == 125
    assert result.infrastructure_error is True
    assert result.output_truncated is True
    assert "combined stdout/stderr exceeded" in (result.policy_violation or "")


@pytest.mark.integration
@pytest.mark.skipif(
    __import__("os").environ.get("RUN_DOCKER_TESTS") != "1",
    reason="set RUN_DOCKER_TESTS=1 with the v0.7.1 runner image available",
)
def test_container_sandbox_real_workspace_growth_limit(tmp_path):
    sandbox = ContainerSandbox(
        tmp_path,
        timeout_seconds=30,
        policy=ContainerPolicy(workspace_write_limit="8k"),
    )

    result = sandbox.run(
        [
            "python",
            "-c",
            "from pathlib import Path; Path('oversized.bin').write_bytes(b'x' * 32768)",
        ]
    )

    assert result.exit_code == 125
    assert result.infrastructure_error is True
    assert "workspace growth exceeded" in (result.policy_violation or "")


@pytest.mark.integration
@pytest.mark.skipif(
    __import__("os").environ.get("RUN_DOCKER_TESTS") != "1",
    reason="set RUN_DOCKER_TESTS=1 with the v0.7.1 runner image available",
)
def test_container_sandbox_real_file_size_ulimit(tmp_path):
    sandbox = ContainerSandbox(
        tmp_path,
        timeout_seconds=30,
        policy=ContainerPolicy(file_size_limit="8k", workspace_write_limit="1m"),
    )

    result = sandbox.run(
        [
            "python",
            "-c",
            "from pathlib import Path; Path('large.bin').write_bytes(b'x' * 32768)",
        ]
    )

    assert result.exit_code != 0
    output = tmp_path / "large.bin"
    assert not output.exists() or output.stat().st_size <= 8192
