from pathlib import Path
import subprocess
import sys


def test_runner_locks_match_declared_cpython_base():
    root = Path(__file__).resolve().parents[1]

    completed = subprocess.run(
        [sys.executable, "scripts/validate_runner_locks.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "passed" in completed.stdout
