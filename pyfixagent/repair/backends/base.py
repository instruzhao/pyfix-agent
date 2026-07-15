from pathlib import Path
from typing import Protocol

from pyfixagent.core.contracts import ApplyResult, RepairMode


class EditBackend(Protocol):
    mode: RepairMode

    def apply(self, workspace: Path, raw_output: str, patch_path: Path) -> ApplyResult:
        """Validate and apply one model proposal."""
