from __future__ import annotations

from pathlib import Path
import time

from pyfixagent.repository.cache import RepositoryIndexStore
from pyfixagent.repository.contracts import RepositoryIndex
from pyfixagent.repository.indexer import RepositoryIndexer


class RepositoryIndexService:
    """Coordinates content fingerprints, persistent cache lookup, and index rebuilds."""

    def __init__(self, indexer: RepositoryIndexer, store: RepositoryIndexStore | None = None):
        self.indexer = indexer
        self.store = store
        self._memory: dict[str, RepositoryIndex] = {}

    def get(self, workspace: Path) -> tuple[RepositoryIndex, dict]:
        started = time.perf_counter()
        root = Path(workspace).resolve()
        snapshot_started = time.perf_counter()
        snapshot = self.indexer.snapshot(root)
        snapshot_seconds = time.perf_counter() - snapshot_started
        store = self.store
        cache_bypassed = False
        if store is not None:
            try:
                store.cache_dir.relative_to(root)
            except ValueError:
                pass
            else:
                store = None
                cache_bypassed = True
        index = self._memory.get(snapshot.fingerprint)
        cache_source = "memory" if index is not None else "miss"
        if index is None and store is not None:
            index = store.load(snapshot.fingerprint)
            if index is not None:
                cache_source = "disk"
        if index is None:
            build_started = time.perf_counter()
            index = self.indexer.build(root, snapshot)
            build_seconds = time.perf_counter() - build_started
            if store is not None:
                store.save(index)
        else:
            build_seconds = 0.0
        self._memory[snapshot.fingerprint] = index
        return index, {
            "cache_hit": cache_source != "miss",
            "cache_source": cache_source,
            "fingerprint": index.fingerprint,
            "cache_bypassed_inside_workspace": cache_bypassed,
            "snapshot_seconds": round(snapshot_seconds, 6),
            "build_seconds": round(build_seconds, 6),
            "total_seconds": round(time.perf_counter() - started, 6),
        }
