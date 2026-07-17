from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from pathlib import Path

from pyfixagent.context.snippet import iter_python_files
from pyfixagent.repository.contracts import DependencyEdge, FileRecord, RepositoryIndex, SymbolRecord


@dataclass(frozen=True)
class SourceSnapshot:
    fingerprint: str
    entries: tuple[tuple[Path, bytes], ...]
    skipped_files: int


class RepositoryIndexer:
    """Builds a deterministic Python index without importing or executing project code."""

    def __init__(
        self,
        *,
        include_tests: bool = True,
        max_files: int = 2000,
        max_file_bytes: int = 1_000_000,
    ):
        self.include_tests = include_tests
        self.max_files = max(1, max_files)
        self.max_file_bytes = max(1, max_file_bytes)

    def snapshot(self, workspace: Path) -> SourceSnapshot:
        root = Path(workspace).resolve()
        digest = hashlib.sha256()
        entries: list[tuple[Path, bytes]] = []
        skipped = 0
        for relative in iter_python_files(root, include_tests=self.include_tests):
            normalized = relative.as_posix().encode("utf-8")
            digest.update(len(normalized).to_bytes(4, "big"))
            digest.update(normalized)
            if len(entries) >= self.max_files:
                digest.update(b"skipped:file-limit")
                skipped += 1
                continue
            try:
                content = (root / relative).read_bytes()
            except OSError:
                digest.update(b"skipped:read-error")
                skipped += 1
                continue
            if len(content) > self.max_file_bytes:
                digest.update(b"skipped:byte-limit")
                digest.update(len(content).to_bytes(8, "big"))
                skipped += 1
                continue
            digest.update(b"indexed")
            digest.update(len(content).to_bytes(8, "big"))
            digest.update(content)
            entries.append((relative, content))
        digest.update(str(self.include_tests).encode("ascii"))
        digest.update(str(self.max_files).encode("ascii"))
        digest.update(str(self.max_file_bytes).encode("ascii"))
        return SourceSnapshot(digest.hexdigest(), tuple(entries), skipped)

    def build(self, workspace: Path, snapshot: SourceSnapshot | None = None) -> RepositoryIndex:
        current = snapshot or self.snapshot(workspace)
        module_by_path = {
            relative.as_posix(): _module_name(relative)
            for relative, _ in current.entries
        }
        path_by_module = {module: path for path, module in module_by_path.items()}
        files: list[FileRecord] = []
        symbols: list[SymbolRecord] = []
        unresolved_imports: dict[str, list[tuple[str, str]]] = {}

        for relative, raw in current.entries:
            path = relative.as_posix()
            module = module_by_path[path]
            content_hash = hashlib.sha256(raw).hexdigest()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError as exc:
                files.append(
                    FileRecord(path, module, content_hash, len(raw), 0, f"UnicodeDecodeError: {exc}")
                )
                continue
            line_count = len(text.splitlines())
            try:
                tree = ast.parse(text, filename=path)
            except SyntaxError as exc:
                message = f"SyntaxError: {exc.msg} at line {exc.lineno or 0}"
                files.append(FileRecord(path, module, content_hash, len(raw), line_count, message))
                continue

            files.append(FileRecord(path, module, content_hash, len(raw), line_count))
            symbols.extend(_collect_symbols(tree, path, module))
            unresolved_imports[path] = _collect_imports(tree, module, relative.name == "__init__.py")

        edges: list[DependencyEdge] = []
        seen_edges: set[tuple[str, str, str]] = set()
        for source_path, imports in unresolved_imports.items():
            for module, imported_name in imports:
                target = _resolve_module_path(module, path_by_module)
                if target is None or target == source_path:
                    continue
                key = (source_path, target, imported_name)
                if key in seen_edges:
                    continue
                seen_edges.add(key)
                edges.append(DependencyEdge(source_path, target, "import", imported_name))

        return RepositoryIndex(
            schema_version="1",
            fingerprint=current.fingerprint,
            files=tuple(sorted(files, key=lambda item: item.path)),
            symbols=tuple(sorted(symbols, key=lambda item: (item.path, item.start_line, item.qualname))),
            edges=tuple(sorted(edges, key=lambda item: (item.source_path, item.target_path, item.imported_name))),
            skipped_files=current.skipped_files,
        )


def _module_name(relative: Path) -> str:
    parts = list(relative.with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _collect_symbols(tree: ast.AST, path: str, module: str) -> list[SymbolRecord]:
    records: list[SymbolRecord] = []

    def add(node: ast.AST, name: str, qualname: str, kind: str) -> None:
        start = max(1, int(getattr(node, "lineno", 1) or 1))
        end = max(start, int(getattr(node, "end_lineno", start) or start))
        records.append(
            SymbolRecord(
                symbol_id=f"{path}:{qualname}",
                path=path,
                module=module,
                name=name,
                qualname=qualname,
                kind=kind,
                start_line=start,
                end_line=end,
            )
        )

    for node in getattr(tree, "body", []):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            add(node, node.name, node.name, "function")
        elif isinstance(node, ast.ClassDef):
            add(node, node.name, node.name, "class")
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    add(child, child.name, f"{node.name}.{child.name}", "method")
    return records


def _collect_imports(tree: ast.AST, module: str, is_package: bool) -> list[tuple[str, str]]:
    imports: list[tuple[str, str]] = []
    package_parts = module.split(".") if is_package else module.split(".")[:-1]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend((alias.name, alias.asname or alias.name) for alias in node.names)
            continue
        if not isinstance(node, ast.ImportFrom):
            continue
        if node.level:
            keep = max(0, len(package_parts) - (node.level - 1))
            prefix = package_parts[:keep]
            if node.module:
                prefix.extend(node.module.split("."))
            base = ".".join(prefix)
        else:
            base = node.module or ""
        for alias in node.names:
            child = ".".join(part for part in (base, alias.name) if part)
            imports.append((child, alias.asname or alias.name))
            if base:
                imports.append((base, alias.asname or alias.name))
    return imports


def _resolve_module_path(module: str, path_by_module: dict[str, str]) -> str | None:
    candidate = module
    while candidate:
        if candidate in path_by_module:
            return path_by_module[candidate]
        candidate = candidate.rpartition(".")[0]
    suffix_matches = sorted(
        (path for known, path in path_by_module.items() if known.endswith(f".{module}")),
    )
    return suffix_matches[0] if len(suffix_matches) == 1 else None
