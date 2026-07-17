from __future__ import annotations

from pathlib import Path

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
        root = Path(workspace).resolve()
        snapshot = self.indexer.snapshot(root)
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
            index = self.indexer.build(root, snapshot)
            if store is not None:
                store.save(index)
        self._memory[snapshot.fingerprint] = index
        return index, {
            "cache_hit": cache_source != "miss",
            "cache_source": cache_source,
            "fingerprint": index.fingerprint,
            "cache_bypassed_inside_workspace": cache_bypassed,
        }
