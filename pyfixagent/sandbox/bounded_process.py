from __future__ import annotations

from dataclasses import dataclass
import subprocess
import threading
import time
from typing import Callable


@dataclass(frozen=True)
class BoundedProcessResult:
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    output_truncated: bool = False
    policy_violation: str | None = None


class _OutputCapture:
    def __init__(self, max_bytes: int):
        self.max_bytes = max_bytes
        self.remaining = max_bytes
        self.stdout = bytearray()
        self.stderr = bytearray()
        self.truncated = False
        self.limit_reached = threading.Event()
        self._lock = threading.Lock()

    def append(self, stream_name: str, chunk: bytes) -> None:
        if not chunk:
            return
        with self._lock:
            accepted = min(self.remaining, len(chunk))
            if accepted:
                target = self.stdout if stream_name == "stdout" else self.stderr
                target.extend(chunk[:accepted])
                self.remaining -= accepted
            if accepted < len(chunk):
                self.truncated = True
                self.limit_reached.set()

    def text(self) -> tuple[str, str]:
        return (
            self.stdout.decode("utf-8", errors="replace"),
            self.stderr.decode("utf-8", errors="replace"),
        )


def run_bounded_process(
    command: list[str],
    *,
    timeout_seconds: int,
    max_output_bytes: int,
    policy_check: Callable[[], str | None] | None = None,
    terminate: Callable[[], None] | None = None,
    poll_interval: float = 0.1,
) -> BoundedProcessResult:
    """Run without a shell while bounding captured output and external policy checks."""
    capture = _OutputCapture(max_output_bytes)
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        stdin=subprocess.DEVNULL,
        text=False,
        shell=False,
    )

    readers = (
        threading.Thread(
            target=_drain_stream,
            args=(process.stdout, "stdout", capture),
            daemon=True,
        ),
        threading.Thread(
            target=_drain_stream,
            args=(process.stderr, "stderr", capture),
            daemon=True,
        ),
    )
    for reader in readers:
        reader.start()

    deadline = time.monotonic() + timeout_seconds
    timed_out = False
    policy_violation: str | None = None
    while process.poll() is None:
        if capture.limit_reached.is_set():
            policy_violation = f"combined stdout/stderr exceeded {max_output_bytes} bytes"
            break
        if policy_check is not None:
            policy_violation = policy_check()
            if policy_violation:
                break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            timed_out = True
            break
        try:
            process.wait(timeout=min(max(0.01, poll_interval), remaining))
        except subprocess.TimeoutExpired:
            pass

    if process.poll() is not None:
        for reader in readers:
            reader.join(timeout=5)
    if policy_violation is None and capture.limit_reached.is_set():
        policy_violation = f"combined stdout/stderr exceeded {max_output_bytes} bytes"
    if not timed_out and policy_violation is None and policy_check is not None:
        policy_violation = policy_check()

    if timed_out or policy_violation:
        if terminate is not None:
            try:
                terminate()
            except Exception:
                pass
        if process.poll() is None:
            try:
                process.kill()
            except Exception:
                pass

    try:
        exit_code = process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        exit_code = 124 if timed_out else 125
    for reader in readers:
        reader.join(timeout=5)

    stdout, stderr = capture.text()
    if timed_out:
        exit_code = 124
    elif policy_violation:
        exit_code = 125
    return BoundedProcessResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        timed_out=timed_out,
        output_truncated=capture.truncated,
        policy_violation=policy_violation,
    )


def _drain_stream(stream, stream_name: str, capture: _OutputCapture) -> None:
    if stream is None:
        return
    try:
        while True:
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            if isinstance(chunk, str):
                chunk = chunk.encode("utf-8", errors="replace")
            capture.append(stream_name, chunk)
    finally:
        try:
            stream.close()
        except Exception:
            pass
