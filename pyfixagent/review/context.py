from __future__ import annotations

from pathlib import Path
import re

from pyfixagent.core.contracts import ContextBundle
from pyfixagent.context.snippet import iter_python_files
from pyfixagent.review.risk_scanner import StructuralRiskScanner


class ReviewContextProvider:
    """Builds changed-file-centered context without accessing external holdouts."""

    def __init__(
        self,
        max_chars: int = 16000,
        include_tests: bool = True,
        risk_scanner: StructuralRiskScanner | None = None,
    ):
        self.max_chars = max(1000, max_chars)
        self.include_tests = include_tests
        self.risk_scanner = risk_scanner or StructuralRiskScanner()

    def build(self, workspace: Path, candidate_diff: str) -> ContextBundle:
        workspace = Path(workspace).resolve()
        changed_paths = self.changed_paths(candidate_diff)
        available = list(iter_python_files(workspace, include_tests=self.include_tests))
        tests = [
            path for path in available
            if path.name.startswith("test_") or "tests" in path.parts
        ]
        ordered: list[tuple[Path, str]] = []
        for raw in changed_paths:
            relative = Path(raw)
            if relative in available:
                ordered.append((relative, "changed_file"))
        for relative in tests:
            if all(relative != existing for existing, _ in ordered):
                ordered.append((relative, "visible_test"))

        rendered: list[str] = []
        selected: list[dict] = []
        source_texts: list[str] = []
        used = 0
        for relative, reason in ordered:
            path = (workspace / relative).resolve()
            try:
                path.relative_to(workspace)
                content = path.read_text(encoding="utf-8")
            except (OSError, UnicodeError, ValueError):
                continue
            header = f"--- {relative.as_posix()} ({reason}) ---\n"
            remaining = self.max_chars - used - len(header)
            if remaining <= 0:
                break
            snippet = content[:remaining]
            rendered.append(header + snippet)
            if reason == "changed_file":
                source_texts.append(content)
            used += len(header) + len(snippet)
            selected.append(
                {
                    "path": relative.as_posix(),
                    "reason": reason,
                    "line_range": [1, max(1, snippet.count("\n") + 1)],
                }
            )

        cues = self.risk_scanner.scan(source_texts)
        cue_text = "\n".join(
            f"- [{cue.cue_id}] {cue.description}" for cue in cues
        ) or "- none"
        body = "\n\n".join(rendered) or "(no review context selected)"
        text = f"Static semantic risk cues (cues are not requirements or verdicts):\n{cue_text}\n\n{body}"
        return ContextBundle(
            rendered=text,
            metadata={
                "purpose": "review",
                "strategy": "changed_files_and_visible_tests",
                "selected_files": selected,
                "changed_paths": changed_paths,
                "structural_risk_cues": [
                    {"id": cue.cue_id, "category": cue.category, "description": cue.description}
                    for cue in cues
                ],
                "stats": {
                    "selected_file_count": len(selected),
                    "selected_context_chars": len(text),
                },
            },
        )

    @staticmethod
    def changed_paths(candidate_diff: str) -> list[str]:
        paths: list[str] = []
        for match in re.finditer(r"^diff --git a/(.*?) b/(.*?)$", candidate_diff, re.MULTILINE):
            path = match.group(2).replace("\\", "/")
            if path.endswith(".py") and path not in paths:
                paths.append(path)
        return paths


def validate_review_evidence(workspace: Path, outcome) -> list[str]:
    """Returns validation errors for reviewer evidence paths and line numbers."""
    root = Path(workspace).resolve()
    errors: list[str] = []
    for risk in outcome.risks:
        for evidence in risk.evidence:
            candidate = (root / str(evidence.get("path", ""))).resolve()
            try:
                candidate.relative_to(root)
            except ValueError:
                errors.append(f"evidence path escapes workspace: {evidence.get('path')}")
                continue
            if not candidate.is_file():
                errors.append(f"evidence path is missing: {evidence.get('path')}")
                continue
            line = evidence.get("line")
            if line is not None:
                try:
                    line_count = len(candidate.read_text(encoding="utf-8").splitlines())
                except (OSError, UnicodeError):
                    errors.append(f"evidence path could not be read: {evidence.get('path')}")
                    continue
                if line > max(1, line_count):
                    errors.append(f"evidence line is outside file: {evidence.get('path')}:{line}")
    return errors
