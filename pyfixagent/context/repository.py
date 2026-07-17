from __future__ import annotations

from collections import deque
from dataclasses import replace
from pathlib import Path
import re

from pyfixagent.context.selector import SelectedContext, SelectedSnippet
from pyfixagent.repository.contracts import DependencyEdge, RepositoryIndex, SymbolRecord
from pyfixagent.repository.service import RepositoryIndexService


class RepositoryContextExpander:
    """Adds deterministic graph neighbors and enforces a source-context token budget."""

    def __init__(
        self,
        service: RepositoryIndexService,
        *,
        max_selected_tokens: int = 12000,
        max_graph_depth: int = 2,
        max_related_files: int = 6,
        max_snippet_lines: int = 200,
    ):
        self.service = service
        self.max_selected_tokens = max(100, max_selected_tokens)
        self.max_graph_depth = max(0, max_graph_depth)
        self.max_related_files = max(0, max_related_files)
        self.max_snippet_lines = max(20, max_snippet_lines)

    def expand(self, workspace: Path, base: SelectedContext, query_text: str = "") -> SelectedContext:
        root = Path(workspace).resolve()
        index, cache = self.service.get(root)
        seeds = [snippet.path for snippet in base.snippets]
        candidates = self._rank_neighbors(index, seeds)
        query = "\n".join([query_text, *(snippet.content for snippet in base.snippets)])
        related: list[SelectedSnippet] = []
        selected_paths = set(seeds)
        for candidate in candidates:
            if len(related) >= self.max_related_files:
                break
            path = candidate["path"]
            if path in selected_paths:
                continue
            snippet = self._read_candidate(root, index, candidate, query)
            if snippet is None:
                continue
            related.append(snippet)
            selected_paths.add(path)

        fitted, estimated_tokens, truncated = self._fit_budget([*base.snippets, *related])
        included_related = sum(1 for snippet in fitted if snippet.reason.startswith("repository_"))
        metadata = {
            "enabled": True,
            "schema_version": index.schema_version,
            **cache,
            "indexed_file_count": len(index.files),
            "symbol_count": len(index.symbols),
            "edge_count": len(index.edges),
            "parse_error_count": len(index.parse_errors),
            "skipped_file_count": index.skipped_files,
            "seed_paths": seeds,
            "related_file_count": included_related,
            "max_graph_depth": self.max_graph_depth,
            "max_selected_tokens": self.max_selected_tokens,
            "estimated_selected_tokens": estimated_tokens,
            "budget_truncated": truncated,
        }
        return SelectedContext(
            strategy=base.strategy,
            snippets=fitted,
            fallback_used=base.fallback_used,
            prompt_chars=base.prompt_chars,
            repository_metadata=metadata,
        )

    def _rank_neighbors(self, index: RepositoryIndex, seeds: list[str]) -> list[dict]:
        outgoing: dict[str, list[DependencyEdge]] = {}
        incoming: dict[str, list[DependencyEdge]] = {}
        for edge in index.edges:
            outgoing.setdefault(edge.source_path, []).append(edge)
            incoming.setdefault(edge.target_path, []).append(edge)

        queue = deque((seed, 0) for seed in seeds)
        best_depth = {seed: 0 for seed in seeds}
        candidates: dict[str, dict] = {}
        while queue:
            path, depth = queue.popleft()
            if depth >= self.max_graph_depth:
                continue
            next_depth = depth + 1
            for edge in sorted(outgoing.get(path, []), key=lambda item: (item.target_path, item.imported_name)):
                self._record_candidate(
                    candidates,
                    edge.target_path,
                    next_depth,
                    "repository_import_dependency",
                    800 - next_depth * 100,
                    edge.imported_name,
                )
                if next_depth < best_depth.get(edge.target_path, self.max_graph_depth + 1):
                    best_depth[edge.target_path] = next_depth
                    queue.append((edge.target_path, next_depth))
            for edge in sorted(incoming.get(path, []), key=lambda item: (item.source_path, item.imported_name)):
                self._record_candidate(
                    candidates,
                    edge.source_path,
                    next_depth,
                    "repository_importer",
                    600 - next_depth * 100,
                    edge.imported_name,
                )
                if next_depth < best_depth.get(edge.source_path, self.max_graph_depth + 1):
                    best_depth[edge.source_path] = next_depth
                    queue.append((edge.source_path, next_depth))
        return sorted(candidates.values(), key=lambda item: (-item["score"], item["path"]))

    @staticmethod
    def _record_candidate(
        candidates: dict[str, dict],
        path: str,
        depth: int,
        reason: str,
        score: int,
        imported_name: str,
    ) -> None:
        current = candidates.get(path)
        candidate = {
            "path": path,
            "depth": depth,
            "reason": reason,
            "score": score,
            "imported_name": imported_name,
        }
        if current is None or (score, -depth, reason) > (
            current["score"],
            -current["depth"],
            current["reason"],
        ):
            candidates[path] = candidate

    def _read_candidate(
        self,
        root: Path,
        index: RepositoryIndex,
        candidate: dict,
        query_text: str,
    ) -> SelectedSnippet | None:
        relative = Path(candidate["path"])
        try:
            path = (root / relative).resolve()
            path.relative_to(root)
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeError, ValueError):
            return None
        if not lines:
            return None
        symbols = [item for item in index.symbols if item.path == candidate["path"]]
        symbol = _best_symbol(symbols, query_text, candidate.get("imported_name", ""))
        if symbol is not None:
            start = max(1, symbol.start_line - 2)
            end = min(len(lines), symbol.end_line + 2)
            symbol_id = symbol.symbol_id
        else:
            start = 1
            end = min(len(lines), self.max_snippet_lines)
            symbol_id = None
        content = "\n".join(lines[start - 1 : end])
        if content:
            content += "\n"
        return SelectedSnippet(
            path=candidate["path"],
            reason=candidate["reason"],
            start_line=start,
            end_line=end,
            content=content,
            score=float(candidate["score"]),
            graph_distance=int(candidate["depth"]),
            symbol=symbol_id,
        )

    def _fit_budget(self, snippets: list[SelectedSnippet]) -> tuple[list[SelectedSnippet], int, bool]:
        remaining = self.max_selected_tokens * 4
        fitted: list[SelectedSnippet] = []
        truncated = False
        for snippet in snippets:
            if remaining <= 0:
                truncated = True
                break
            if len(snippet.content) <= remaining:
                fitted.append(snippet)
                remaining -= len(snippet.content)
                continue
            content = snippet.content[:remaining]
            if "\n" in content:
                content = content.rsplit("\n", 1)[0] + "\n"
            if not content:
                truncated = True
                break
            end = snippet.start_line + max(0, content.count("\n") - 1)
            fitted.append(replace(snippet, content=content, end_line=max(snippet.start_line, end)))
            remaining -= len(content)
            truncated = True
            break
        characters = sum(len(snippet.content) for snippet in fitted)
        return fitted, _estimate_tokens(characters), truncated


def _best_symbol(
    symbols: list[SymbolRecord],
    query_text: str,
    imported_name: str,
) -> SymbolRecord | None:
    query = query_text.casefold()
    imported = imported_name.casefold()
    ranked: list[tuple[int, int, str, SymbolRecord]] = []
    for symbol in symbols:
        name = symbol.name.casefold()
        score = 0
        if imported and name == imported:
            score += 100
        score += min(20, len(re.findall(rf"\b{re.escape(name)}\b", query))) * 5
        if score:
            ranked.append((score, -(symbol.end_line - symbol.start_line), symbol.qualname, symbol))
    if not ranked:
        return None
    return max(ranked, key=lambda item: (item[0], item[1], item[2]))[3]


def _estimate_tokens(characters: int) -> int:
    return (max(0, characters) + 3) // 4
