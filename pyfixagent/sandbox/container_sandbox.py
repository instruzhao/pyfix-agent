from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import uuid

from pyfixagent.sandbox.base import CommandResult
from pyfixagent.sandbox.policy import is_command_allowed


_IMAGE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/:@-]*$")
_SIZE_PATTERN = re.compile(r"^[1-9][0-9]*(?:[kKmMgG])?[bB]?$|^[1-9][0-9]*$")
_USER_PATTERN = re.compile(r"^[1-9][0-9]*(?::[1-9][0-9]*)?$")


@dataclass(frozen=True)
class ContainerPolicy:
    engine: str = "docker"
    image: str = "pyfixagent-runner:0.7.0"
    pull_policy: str = "never"
    network: str = "none"
    cpus: float = 1.0
    memory: str = "1g"
    pids_limit: int = 128
    read_only_root: bool = True
    tmpfs_size: str = "128m"
    user: str = "65534:65534"
    dependency_policy: str = "image_only"

    def __post_init__(self) -> None:
        if self.engine not in {"docker", "podman"}:
            raise ValueError("container engine must be docker or podman")
        if not _IMAGE_PATTERN.fullmatch(self.image) or self.image.startswith("-"):
            raise ValueError(f"invalid container image reference: {self.image}")
        if self.pull_policy not in {"never", "missing"}:
            raise ValueError("container pull_policy must be never or missing")
        if self.network not in {"none", "bridge"}:
            raise ValueError("container network must be none or bridge")
        if self.cpus <= 0:
            raise ValueError("container cpus must be positive")
        if not _SIZE_PATTERN.fullmatch(self.memory):
            raise ValueError("container memory must be a positive Docker size such as 1g")
        if self.pids_limit < 1:
            raise ValueError("container pids_limit must be positive")
        if not _SIZE_PATTERN.fullmatch(self.tmpfs_size):
            raise ValueError("container tmpfs_size must be a positive Docker size such as 128m")
        if self.dependency_policy != "image_only":
            raise ValueError("v0.7.0 supports only the image_only dependency policy")
        if not _USER_PATTERN.fullmatch(self.user):
            raise ValueError("container user must be an explicit non-root uid[:gid]")


class ContainerSandbox:
    """Runs allowed test commands in an ephemeral, resource-bounded container."""

    backend = "container"

    def __init__(
        self,
        workspace: Path,
        timeout_seconds: int = 30,
        policy: ContainerPolicy | None = None,
    ):
        self.workspace = Path(workspace)
        self.timeout_seconds = max(1, int(timeout_seconds))
        self.policy = policy or ContainerPolicy()
        self._runtime_metadata: dict | None = None
        self._runtime_ready: bool | None = None

    def with_workspace(self, workspace: Path) -> "ContainerSandbox":
        rebound = ContainerSandbox(
            Path(workspace),
            timeout_seconds=self.timeout_seconds,
            policy=self.policy,
        )
        rebound._runtime_metadata = self._runtime_metadata
        rebound._runtime_ready = self._runtime_ready
        return rebound

    def pytest_basetemp(self, host_root: Path, index: int) -> str:
        return f"/tmp/pyfixagent-pytest-{index}"

    def run(self, command: list[str], timeout: int | None = None) -> CommandResult:
        start = time.perf_counter()
        timeout_seconds = max(1, int(timeout or self.timeout_seconds))
        allowed, reason = is_command_allowed(command)
        if not allowed:
            return CommandResult(
                command=list(command),
                exit_code=126,
                stdout="",
                stderr=reason or "command is not allowed",
                duration=time.perf_counter() - start,
                backend=self.backend,
                infrastructure_error=True,
            )
        if _is_dependency_install(command):
            return CommandResult(
                command=list(command),
                exit_code=126,
                stdout="",
                stderr="runtime dependency installation is blocked by the image_only policy",
                duration=time.perf_counter() - start,
                backend=self.backend,
                infrastructure_error=True,
            )
        if shutil.which(self.policy.engine) is None:
            return CommandResult(
                command=list(command),
                exit_code=127,
                stdout="",
                stderr=f"container runtime is not installed or not on PATH: {self.policy.engine}",
                duration=time.perf_counter() - start,
                backend=self.backend,
                infrastructure_error=True,
            )
        ready, runtime_error = self._preflight_runtime(timeout_seconds)
        if not ready:
            return CommandResult(
                command=list(command),
                exit_code=125,
                stdout="",
                stderr=runtime_error or "container runtime daemon is unavailable",
                duration=time.perf_counter() - start,
                backend=self.backend,
                infrastructure_error=True,
            )

        workspace = self.workspace.resolve()
        if not workspace.is_dir():
            return CommandResult(
                command=list(command),
                exit_code=1,
                stdout="",
                stderr=f"container workspace does not exist: {workspace}",
                duration=time.perf_counter() - start,
                backend=self.backend,
                infrastructure_error=True,
            )

        container_name = f"pyfixagent-{uuid.uuid4().hex[:12]}"
        runtime_command = self._build_runtime_command(command, workspace, container_name)
        try:
            completed = subprocess.run(
                runtime_command,
                timeout=timeout_seconds,
                capture_output=True,
                text=True,
                check=False,
            )
            return CommandResult(
                command=list(command),
                exit_code=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
                duration=time.perf_counter() - start,
                backend=self.backend,
                runtime_command=runtime_command,
                infrastructure_error=completed.returncode in {125, 126, 127},
            )
        except subprocess.TimeoutExpired as exc:
            self._force_remove(container_name)
            return CommandResult(
                command=list(command),
                exit_code=124,
                stdout=_subprocess_text(exc.stdout),
                stderr=_subprocess_text(exc.stderr) or f"container command timed out after {timeout_seconds}s",
                duration=time.perf_counter() - start,
                timeout=True,
                backend=self.backend,
                runtime_command=runtime_command,
            )
        except Exception as exc:
            return CommandResult(
                command=list(command),
                exit_code=1,
                stdout="",
                stderr=f"failed to run container command: {exc}",
                duration=time.perf_counter() - start,
                backend=self.backend,
                runtime_command=runtime_command,
                infrastructure_error=True,
            )

    def environment_metadata(self) -> dict:
        if self._runtime_metadata is None or (
            self._runtime_ready is True and self._runtime_metadata.get("image_resolved") is None
        ):
            self._runtime_metadata = self._inspect_runtime()
        return {
            "backend": self.backend,
            "isolation": "ephemeral_container",
            "timeout_seconds": self.timeout_seconds,
            "workspace_mount": "rw:/workspace",
            "root_filesystem": "read_only" if self.policy.read_only_root else "writable",
            "network": self.policy.network,
            "dependency_policy": self.policy.dependency_policy,
            "policy": asdict(self.policy),
            **self._runtime_metadata,
        }

    def _build_runtime_command(
        self,
        command: list[str],
        workspace: Path,
        container_name: str,
    ) -> list[str]:
        policy = self.policy
        runtime = [
            policy.engine,
            "run",
            "--rm",
            "--name",
            container_name,
            "--pull",
            policy.pull_policy,
            "--workdir",
            "/workspace",
            "--mount",
            f"type=bind,source={workspace},target=/workspace",
            "--network",
            policy.network,
            "--cpus",
            str(policy.cpus),
            "--memory",
            policy.memory,
            "--pids-limit",
            str(policy.pids_limit),
            "--security-opt",
            "no-new-privileges:true",
            "--cap-drop",
            "ALL",
            "--user",
            policy.user,
            "--env",
            "HOME=/tmp",
            "--env",
            "PYTHONDONTWRITEBYTECODE=1",
            "--env",
            "PYTHONPATH=/workspace",
        ]
        if policy.read_only_root:
            runtime.extend(
                [
                    "--read-only",
                    "--tmpfs",
                    f"/tmp:rw,noexec,nosuid,nodev,size={policy.tmpfs_size}",
                ]
            )
        runtime.append(policy.image)
        runtime.extend(_container_command(command))
        return runtime

    def _inspect_runtime(self) -> dict:
        if shutil.which(self.policy.engine) is None:
            return {
                "engine": self.policy.engine,
                "engine_available": False,
                "image_requested": self.policy.image,
                "image_resolved": None,
            }
        server_version = _best_effort_output(
            [self.policy.engine, "version", "--format", "{{.Server.Version}}"]
        )
        image_json = _best_effort_output(
            [self.policy.engine, "image", "inspect", "--format", "{{json .}}", self.policy.image]
        )
        image_resolved = None
        image_id = None
        if image_json:
            try:
                data = json.loads(image_json)
            except json.JSONDecodeError:
                data = {}
            repo_digests = data.get("RepoDigests") or []
            image_resolved = repo_digests[0] if repo_digests else data.get("Id")
            image_id = data.get("Id")
        return {
            "engine": self.policy.engine,
            "engine_available": bool(server_version),
            "engine_server_version": server_version or None,
            "image_requested": self.policy.image,
            "image_resolved": image_resolved,
            "image_id": image_id,
        }

    def _preflight_runtime(self, command_timeout: int) -> tuple[bool, str | None]:
        if self._runtime_ready is not None:
            return self._runtime_ready, None if self._runtime_ready else "container runtime daemon is unavailable"
        command = [self.policy.engine, "version", "--format", "{{.Server.Version}}"]
        try:
            completed = subprocess.run(
                command,
                timeout=min(10, command_timeout),
                capture_output=True,
                text=True,
                check=False,
            )
        except subprocess.TimeoutExpired:
            self._runtime_ready = False
            self._runtime_metadata = self._unavailable_runtime_metadata()
            return False, "container runtime daemon preflight timed out"
        except Exception as exc:
            self._runtime_ready = False
            self._runtime_metadata = self._unavailable_runtime_metadata()
            return False, f"container runtime daemon preflight failed: {exc}"
        server_version = completed.stdout.strip()
        self._runtime_ready = completed.returncode == 0 and bool(server_version)
        if not self._runtime_ready:
            self._runtime_metadata = self._unavailable_runtime_metadata()
            error = completed.stderr.strip() or "container runtime daemon is unavailable"
            return False, error
        self._runtime_metadata = {
            "engine": self.policy.engine,
            "engine_available": True,
            "engine_server_version": server_version,
            "image_requested": self.policy.image,
            "image_resolved": None,
            "image_id": None,
        }
        return True, None

    def _unavailable_runtime_metadata(self) -> dict:
        return {
            "engine": self.policy.engine,
            "engine_available": False,
            "engine_server_version": None,
            "image_requested": self.policy.image,
            "image_resolved": None,
            "image_id": None,
        }

    def _force_remove(self, container_name: str) -> None:
        try:
            subprocess.run(
                [self.policy.engine, "rm", "--force", container_name],
                timeout=10,
                capture_output=True,
                text=True,
                check=False,
            )
        except Exception:
            pass


def _container_command(command: list[str]) -> list[str]:
    if not command:
        return []
    executable = Path(command[0]).name.lower()
    if executable in {"python.exe", "python3.exe"}:
        executable = executable.removesuffix(".exe")
    elif executable == "pytest.exe":
        executable = "pytest"
    return [executable, *command[1:]]


def _is_dependency_install(command: list[str]) -> bool:
    lowered = [Path(part).name.lower() for part in command]
    if not lowered:
        return False
    if lowered[0] in {"pip", "pip.exe", "pip3", "pip3.exe", "poetry", "uv"}:
        return True
    return len(lowered) >= 3 and lowered[0] in {
        "python",
        "python.exe",
        "python3",
        "python3.exe",
    } and lowered[1:3] == ["-m", "pip"]


def _subprocess_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _best_effort_output(command: list[str]) -> str:
    try:
        completed = subprocess.run(
            command,
            timeout=10,
            capture_output=True,
            text=True,
            check=False,
        )
    except Exception:
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""
