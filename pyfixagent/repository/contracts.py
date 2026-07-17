from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class FileRecord:
    path: str
    module: str
    sha256: str
    size_bytes: int
    line_count: int
    parse_error: str | None = None


@dataclass(frozen=True)
class SymbolRecord:
    symbol_id: str
    path: str
    module: str
    name: str
    qualname: str
    kind: str
    start_line: int
    end_line: int


@dataclass(frozen=True)
class DependencyEdge:
    source_path: str
    target_path: str
    kind: str = "import"
    imported_name: str = ""


@dataclass(frozen=True)
class RepositoryIndex:
    schema_version: str
    fingerprint: str
    files: tuple[FileRecord, ...]
    symbols: tuple[SymbolRecord, ...]
    edges: tuple[DependencyEdge, ...]
    skipped_files: int = 0

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "fingerprint": self.fingerprint,
            "files": [asdict(item) for item in self.files],
            "symbols": [asdict(item) for item in self.symbols],
            "edges": [asdict(item) for item in self.edges],
            "skipped_files": self.skipped_files,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RepositoryIndex":
        if str(data.get("schema_version")) != "1":
            raise ValueError("unsupported repository index schema")
        return cls(
            schema_version="1",
            fingerprint=str(data["fingerprint"]),
            files=tuple(FileRecord(**item) for item in data.get("files", [])),
            symbols=tuple(SymbolRecord(**item) for item in data.get("symbols", [])),
            edges=tuple(DependencyEdge(**item) for item in data.get("edges", [])),
            skipped_files=max(0, int(data.get("skipped_files", 0))),
        )

    @property
    def parse_errors(self) -> tuple[FileRecord, ...]:
        return tuple(item for item in self.files if item.parse_error)
