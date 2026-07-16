from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContextPlan:
    strategy: str
    line_window: int
    max_files: int
    level: int = 0


class ContextExpansionPolicy:
    """Expands context after semantic retries without selecting files itself."""

    def __init__(self, max_level: int = 2):
        self.max_level = max(0, max_level)
        self.level = 0
        self.last_reason: str | None = None

    def expand(self, reason: str) -> int:
        self.level = min(self.max_level, self.level + 1)
        self.last_reason = reason
        return self.level

    def plan(
        self,
        *,
        strategy: str,
        line_window: int,
        max_files: int,
        allow_full: bool,
    ) -> ContextPlan:
        if strategy == "full":
            return ContextPlan("full", line_window, max_files, self.level)
        if self.level >= 2 and allow_full:
            return ContextPlan("full", line_window, max_files, self.level)
        multiplier = 2 if self.level >= 1 else 1
        return ContextPlan(
            strategy="traceback",
            line_window=max(0, line_window) * multiplier,
            max_files=max(1, max_files) * multiplier,
            level=self.level,
        )
