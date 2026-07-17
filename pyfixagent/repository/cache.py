from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile

from pyfixagent.repository.contracts import RepositoryIndex


class RepositoryIndexStore:
    """Stores content-addressed indexes outside the workspace being repaired."""

    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir).resolve()

    def load(self, fingerprint: str) -> RepositoryIndex | None:
        path = self._path(fingerprint)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            index = RepositoryIndex.from_dict(data)
        except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
            return None
        return index if index.fingerprint == fingerprint else None

    def save(self, index: RepositoryIndex) -> Path:
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        target = self._path(index.fingerprint)
        payload = json.dumps(index.to_dict(), ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        handle, raw_temp = tempfile.mkstemp(prefix="repository-index-", suffix=".tmp", dir=self.cache_dir)
        temp_path = Path(raw_temp)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(payload)
            os.replace(temp_path, target)
        finally:
            if temp_path.exists():
                temp_path.unlink()
        return target

    def _path(self, fingerprint: str) -> Path:
        safe = "".join(character for character in fingerprint.lower() if character in "0123456789abcdef")
        if len(safe) < 16:
            raise ValueError("invalid repository fingerprint")
        return self.cache_dir / f"repository-index-v1-{safe}.json"
