from __future__ import annotations

from pathlib import Path


DEFAULT_TEST_COMMAND = ("python", "-m", "pytest", "-p", "no:cacheprovider")
_SHELL_TOKENS = {"&&", "||", "|", ";", ">", ">>", "<", "<<"}


class TestCommandPolicy:
    """Validates argv-only pytest commands before the local runner executes them."""

    def validate(self, command: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(str(part) for part in command)
        if not normalized or any(not part.strip() for part in normalized):
            raise ValueError("test command must be a non-empty argv list")
        if any(part in _SHELL_TOKENS or "\n" in part or "\r" in part for part in normalized):
            raise ValueError("test command must not contain shell operators")

        executable = Path(normalized[0]).name.lower()
        if executable in {"pytest", "pytest.exe"}:
            return normalized
        if executable in {"python", "python.exe", "python3", "python3.exe"}:
            if len(normalized) >= 3 and normalized[1:3] == ("-m", "pytest"):
                return normalized
        raise ValueError("test command must invoke pytest directly or through python -m pytest")


def normalize_test_commands(raw_commands) -> tuple[tuple[str, ...], ...]:
    if raw_commands is None:
        return (DEFAULT_TEST_COMMAND,)
    if not isinstance(raw_commands, list) or not raw_commands:
        raise ValueError("test.commands must be a non-empty list of argv lists")
    policy = TestCommandPolicy()
    commands: list[tuple[str, ...]] = []
    for raw in raw_commands:
        if not isinstance(raw, list):
            raise ValueError("each test command must be an argv list, not a shell string")
        commands.append(policy.validate(raw))
    return tuple(commands)
