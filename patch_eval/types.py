from dataclasses import dataclass, field


EMPTY_OUTPUT = "EMPTY_OUTPUT"
JSON_PARSE_ERROR = "JSON_PARSE_ERROR"
NO_PATCH_FOUND = "NO_PATCH_FOUND"
MARKDOWN_FENCE_FOUND = "MARKDOWN_FENCE_FOUND"
MISSING_DIFF_GIT_HEADER = "MISSING_DIFF_GIT_HEADER"
MISSING_DIFF_GIT_HEADER_NORMALIZED = "MISSING_DIFF_GIT_HEADER_NORMALIZED"
MISSING_FILE_HEADER = "MISSING_FILE_HEADER"
MISSING_HUNK_HEADER = "MISSING_HUNK_HEADER"
UNSUPPORTED_CREATE_DELETE = "UNSUPPORTED_CREATE_DELETE"
UNSAFE_PATH = "UNSAFE_PATH"
SPECIAL_WHITESPACE_FOUND = "SPECIAL_WHITESPACE_FOUND"
GIT_APPLY_CHECK_FAILED = "GIT_APPLY_CHECK_FAILED"
CORRUPT_PATCH = "CORRUPT_PATCH"
PATCH_CONTEXT_MISMATCH = "PATCH_CONTEXT_MISMATCH"


@dataclass
class ParseResult:
    cleaned_patch: str | None
    source_type: str | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class NormalizeResult:
    normalized_patch: str | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    ok: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class GitApplyResult:
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    error_type: str | None
    command: str = "git apply --check -"


@dataclass
class EvaluationResult:
    ok: bool
    cleaned_patch: str | None
    normalized_patch: str | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error_type: str | None = None
    git_apply_stdout: str | None = None
    git_apply_stderr: str | None = None
    git_apply_command: str = "git apply --check -"
