import sys
import time

from pyfixagent.sandbox.bounded_process import run_bounded_process


def test_bounded_process_returns_normal_output():
    result = run_bounded_process(
        [sys.executable, "-c", "print('ok')"],
        timeout_seconds=5,
        max_output_bytes=1024,
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "ok"
    assert result.output_truncated is False
    assert result.policy_violation is None


def test_bounded_process_stops_after_combined_output_limit():
    result = run_bounded_process(
        [sys.executable, "-c", "import sys; sys.stdout.write('x' * 65536)"],
        timeout_seconds=5,
        max_output_bytes=4096,
    )

    assert result.exit_code == 125
    assert len(result.stdout.encode("utf-8")) <= 4096
    assert result.output_truncated is True
    assert "exceeded 4096 bytes" in (result.policy_violation or "")


def test_bounded_process_enforces_timeout_and_termination_callback():
    terminated: list[bool] = []
    result = run_bounded_process(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        timeout_seconds=1,
        max_output_bytes=1024,
        terminate=lambda: terminated.append(True),
    )

    assert result.exit_code == 124
    assert result.timed_out is True
    assert terminated == [True]


def test_bounded_process_enforces_external_policy_check():
    started = time.monotonic()

    def check_policy():
        if time.monotonic() - started > 0.1:
            return "workspace growth exceeded 1024 bytes"
        return None

    result = run_bounded_process(
        [sys.executable, "-c", "import time; time.sleep(10)"],
        timeout_seconds=5,
        max_output_bytes=1024,
        policy_check=check_policy,
    )

    assert result.exit_code == 125
    assert result.policy_violation == "workspace growth exceeded 1024 bytes"
