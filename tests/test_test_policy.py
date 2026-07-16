import pytest

from pyfixagent.execution.test_policy import TestCommandPolicy, normalize_test_commands
from pyfixagent.execution.test_runner import TestRunner as VisibleTestRunner
from pyfixagent.sandbox.local_sandbox import LocalSandbox


def test_test_command_policy_accepts_argv_pytest_commands():
    policy = TestCommandPolicy()

    assert policy.validate(["pytest", "-q"]) == ("pytest", "-q")
    assert policy.validate(["python", "-m", "pytest", "tests/unit"]) == (
        "python",
        "-m",
        "pytest",
        "tests/unit",
    )


@pytest.mark.parametrize(
    "command",
    [
        ["python", "script.py"],
        ["powershell", "pytest"],
        ["pytest", "&&", "echo", "unsafe"],
        ["pytest -q"],
    ],
)
def test_test_command_policy_rejects_non_pytest_or_shell_commands(command):
    with pytest.raises(ValueError):
        TestCommandPolicy().validate(command)


def test_test_command_config_rejects_shell_strings():
    with pytest.raises(ValueError, match="argv list"):
        normalize_test_commands(["pytest -q"])


def test_test_runner_stops_at_first_failing_configured_command(tmp_path):
    (tmp_path / "test_one.py").write_text("def test_failure():\n    assert False\n", encoding="utf-8")
    (tmp_path / "test_two.py").write_text("def test_success():\n    assert True\n", encoding="utf-8")
    runner = VisibleTestRunner(
        LocalSandbox(tmp_path),
        commands=(("python", "-m", "pytest", "-q", "test_one.py"), ("pytest", "-q", "test_two.py")),
    )

    result = runner.run()

    assert result.success is False
    assert len(result.command_results) == 1
    assert result.command_results[0].command[-1] == "test_one.py"
