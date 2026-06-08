from dataclasses import dataclass
import re


@dataclass
class TraceFrame:
    path: str
    line: int | None
    function: str | None = None
    raw: str | None = None


@dataclass
class PytestFailureSummary:
    failed_tests: list[str]
    exception_type: str | None
    error_message: str | None
    frames: list[TraceFrame]
    raw_output: str


_FAILED_TEST_RE = re.compile(r"^\s*FAILED\s+(?P<node>\S+)")
_TRACE_FRAME_RE = re.compile(
    r"^\s*(?:E\s+)?(?P<path>(?:[A-Za-z]:)?[^:\n]+?\.py):(?P<line>\d+)"
    r"(?::\s+in\s+(?P<function>[^\n]+))?"
)
_EXCEPTION_RE = re.compile(
    r"^\s*(?:E\s+)?(?P<type>[A-Za-z_][A-Za-z0-9_.]*(?:Error|Exception|Warning|Failure|Failed))"
    r"(?::\s*(?P<message>.*))?$"
)


def parse_pytest_failure_output(output: str) -> PytestFailureSummary:
    failed_tests: list[str] = []
    frames: list[TraceFrame] = []
    exception_type: str | None = None
    error_message: str | None = None

    for raw_line in output.splitlines():
        line = raw_line.strip()
        failed_match = _FAILED_TEST_RE.match(raw_line)
        if failed_match:
            node = failed_match.group("node")
            if node not in failed_tests:
                failed_tests.append(node)

        frame_match = _TRACE_FRAME_RE.match(line)
        if frame_match:
            frames.append(
                TraceFrame(
                    path=_normalize_path(frame_match.group("path")),
                    line=int(frame_match.group("line")),
                    function=_clean_function(frame_match.group("function")),
                    raw=raw_line,
                )
            )

        exception_match = _EXCEPTION_RE.match(line)
        if exception_match:
            exception_type = exception_match.group("type")
            message = exception_match.group("message")
            error_message = message if message is not None else ""

    return PytestFailureSummary(
        failed_tests=failed_tests,
        exception_type=exception_type,
        error_message=error_message,
        frames=frames,
        raw_output=output,
    )


def _normalize_path(path: str) -> str:
    return path.strip().replace("\\", "/")


def _clean_function(function: str | None) -> str | None:
    if function is None:
        return None
    cleaned = function.strip()
    return cleaned or None
