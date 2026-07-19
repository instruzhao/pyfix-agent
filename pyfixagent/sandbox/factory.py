from __future__ import annotations

from pathlib import Path

from pyfixagent.sandbox.base import Sandbox
from pyfixagent.sandbox.container_sandbox import ContainerPolicy, ContainerSandbox
from pyfixagent.sandbox.local_sandbox import LocalSandbox


SANDBOX_BACKENDS = {"local", "container"}


def build_sandbox(
    workspace: Path,
    sandbox_config: dict | None = None,
    *,
    backend_override: str | None = None,
    container_image_override: str | None = None,
) -> Sandbox:
    config = dict(sandbox_config or {})
    backend = str(backend_override or config.get("backend", "container")).strip().lower()
    if backend not in SANDBOX_BACKENDS:
        raise ValueError(f"sandbox backend must be one of: {', '.join(sorted(SANDBOX_BACKENDS))}")
    timeout_seconds = max(1, int(config.get("timeout_seconds", 30)))
    if backend == "local":
        return LocalSandbox(workspace, timeout_seconds=timeout_seconds)

    container = dict(config.get("container", {}) or {})
    policy = ContainerPolicy(
        engine=str(container.get("engine", "docker")),
        image=str(container_image_override or container.get("image", "pyfixagent-runner:0.7.1")),
        pull_policy=str(container.get("pull_policy", "never")),
        network=str(container.get("network", "none")),
        cpus=float(container.get("cpus", 1.0)),
        memory=str(container.get("memory", "1g")),
        pids_limit=int(container.get("pids_limit", 128)),
        read_only_root=_as_bool(container.get("read_only_root", True)),
        tmpfs_size=str(container.get("tmpfs_size", "128m")),
        output_limit=str(container.get("output_limit", "4m")),
        workspace_write_limit=str(container.get("workspace_write_limit", "256m")),
        file_size_limit=str(container.get("file_size_limit", "64m")),
        open_files_limit=int(container.get("open_files_limit", 1024)),
        user=str(container.get("user", "workspace_owner")),
        dependency_policy=str(container.get("dependency_policy", "image_only")),
    )
    return ContainerSandbox(workspace, timeout_seconds=timeout_seconds, policy=policy)


def _as_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
