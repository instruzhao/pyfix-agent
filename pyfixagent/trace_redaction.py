from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
from typing import Any


TRACE_REDACTION_MODES = {"none", "paths", "safe"}

_CONTENT_KEYS = {
    "task",
    "prompt",
    "raw_model_output",
    "cleaned_patch",
    "pytest_output",
    "test_output_before",
    "test_output_after",
    "patch",
    "candidate_patch",
    "replacement_raw_output",
    "generated_diff",
}
_CONTENT_CONTAINER_KEYS = {"model_output", "replacement_edits"}


class TraceRedactor:
    """Redacts local paths and, in safe mode, source-bearing trace payloads."""

    def __init__(self, mode: str = "paths"):
        normalized = str(mode).strip().lower()
        if normalized not in TRACE_REDACTION_MODES:
            raise ValueError(f"trace redaction mode must be one of: {', '.join(sorted(TRACE_REDACTION_MODES))}")
        self.mode = normalized
        self._redacted_fields: set[str] = set()

    def redact(self, trace: dict, *, workspace: str | Path | None = None) -> dict:
        self._redacted_fields.clear()
        if self.mode == "none":
            trace["trace_redaction"] = {"mode": "none", "redacted_fields": []}
            return trace
        replacements = self._path_replacements(workspace)
        redacted = self._walk(trace, replacements)
        redacted["trace_redaction"] = {
            "mode": self.mode,
            "redacted_fields": sorted(self._redacted_fields),
            "path_placeholder_count": len(replacements),
        }
        return redacted

    def _walk(self, value: Any, replacements: tuple[tuple[str, str], ...], key: str = "") -> Any:
        if self.mode == "safe" and key in _CONTENT_KEYS and isinstance(value, str) and value:
            self._redacted_fields.add(key)
            return _content_marker(value)
        if self.mode == "safe" and key in _CONTENT_CONTAINER_KEYS and value:
            self._redacted_fields.add(key)
            serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            return _content_marker(serialized)
        if isinstance(value, dict):
            return {item_key: self._walk(item, replacements, item_key) for item_key, item in value.items()}
        if isinstance(value, list):
            return [self._walk(item, replacements, key) for item in value]
        if isinstance(value, tuple):
            return [self._walk(item, replacements, key) for item in value]
        if isinstance(value, str):
            return _replace_paths(value, replacements)
        return value

    @staticmethod
    def _path_replacements(workspace: str | Path | None) -> tuple[tuple[str, str], ...]:
        raw: list[tuple[str, str]] = []
        if workspace:
            raw.append((str(workspace), "<workspace>"))
            raw.append((str(Path(workspace).resolve()), "<workspace>"))
        raw.append((str(Path.cwd().resolve()), "<project-root>"))
        raw.append((str(Path.home().resolve()), "<home>"))
        deduplicated: dict[str, str] = {}
        for path, placeholder in raw:
            if path:
                deduplicated.setdefault(path, placeholder)
                deduplicated.setdefault(path.replace("\\", "/"), placeholder)
        return tuple(sorted(deduplicated.items(), key=lambda item: len(item[0]), reverse=True))


def _replace_paths(value: str, replacements: tuple[tuple[str, str], ...]) -> str:
    result = value
    for path, placeholder in replacements:
        result = re.sub(re.escape(path), placeholder, result, flags=re.IGNORECASE)
    return result


def _content_marker(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"<redacted sha256={digest} chars={len(value)}>"
