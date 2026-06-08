from dataclasses import dataclass
import re


@dataclass
class PytestSummary:
    total: int | None
    passed: int
    failed: int
    skipped: int
    failed_tests: list[str]


_COLLECTED_RE = re.compile(r"\bcollected\s+(?P<count>\d+)\s+items?\b")
_FAILED_NODE_RE = re.compile(r"^\s*FAILED\s+(?P<node>\S+)")
_COUNT_RE = re.compile(r"(?P<count>\d+)\s+(?P<kind>failed|passed|skipped|error|errors)\b")


def parse_pytest_summary(output: str) -> PytestSummary:
    total: int | None = None
    counts = {"passed": 0, "failed": 0, "skipped": 0}
    failed_tests: list[str] = []

    for raw_line in output.splitlines():
        collected_match = _COLLECTED_RE.search(raw_line)
        if collected_match:
            total = int(collected_match.group("count"))

        failed_match = _FAILED_NODE_RE.match(raw_line)
        if failed_match:
            node = _normalize_node_id(failed_match.group("node"))
            if node not in failed_tests:
                failed_tests.append(node)

    for line in reversed(output.splitlines()):
        line_counts = list(_COUNT_RE.finditer(line))
        if not line_counts:
            continue
        for match in line_counts:
            kind = match.group("kind")
            count = int(match.group("count"))
            if kind == "passed":
                counts["passed"] = count
            elif kind == "skipped":
                counts["skipped"] = count
            elif kind in {"failed", "error", "errors"}:
                counts["failed"] += count
        break

    if total is None:
        inferred_total = counts["passed"] + counts["failed"] + counts["skipped"]
        total = inferred_total if inferred_total else None

    return PytestSummary(
        total=total,
        passed=counts["passed"],
        failed=counts["failed"],
        skipped=counts["skipped"],
        failed_tests=failed_tests,
    )


def pytest_summary_to_dict(summary: PytestSummary | None) -> dict | None:
    if summary is None:
        return None
    return {
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "skipped": summary.skipped,
        "failed_tests": list(summary.failed_tests),
    }


def short_test_result(summary: PytestSummary | None) -> str:
    if summary is None:
        return "unknown"
    parts: list[str] = []
    if summary.failed:
        parts.append(f"{summary.failed} failed")
    if summary.passed:
        parts.append(f"{summary.passed} passed")
    if summary.skipped:
        parts.append(f"{summary.skipped} skipped")
    return ", ".join(parts) if parts else "no tests parsed"


def _normalize_node_id(node: str) -> str:
    return node.replace("\\", "/")
