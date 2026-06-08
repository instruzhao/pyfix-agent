from pathlib import PurePosixPath

from patch_eval.types import (
    EMPTY_OUTPUT,
    MARKDOWN_FENCE_FOUND,
    MISSING_DIFF_GIT_HEADER,
    MISSING_FILE_HEADER,
    MISSING_HUNK_HEADER,
    SPECIAL_WHITESPACE_FOUND,
    UNSAFE_PATH,
    UNSUPPORTED_CREATE_DELETE,
    ValidationResult,
)


def validate_patch_format(normalized_patch: str) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    text = normalized_patch or ""

    if not text.strip():
        return ValidationResult(ok=False, errors=[EMPTY_OUTPUT])
    if "```" in text:
        errors.append(MARKDOWN_FENCE_FOUND)
    if "\xa0" in text or "\u3000" in text:
        errors.append(SPECIAL_WHITESPACE_FOUND)
    if "/dev/null" in text:
        errors.append(UNSUPPORTED_CREATE_DELETE)
    if "diff --git " not in text:
        errors.append(MISSING_DIFF_GIT_HEADER)

    lines = text.splitlines()
    diff_indexes = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    for block_number, start in enumerate(diff_indexes):
        end = diff_indexes[block_number + 1] if block_number + 1 < len(diff_indexes) else len(lines)
        block = lines[start:end]
        parts = block[0].split()
        if len(parts) < 4:
            errors.append(MISSING_DIFF_GIT_HEADER)
        else:
            for path in parts[2:4]:
                if _is_unsafe_diff_path(path):
                    errors.append(UNSAFE_PATH)

        file_headers = [line for line in block if line.startswith(("--- ", "+++ "))]
        if not any(line.startswith("--- ") for line in block) or not any(line.startswith("+++ ") for line in block):
            errors.append(MISSING_FILE_HEADER)
        for header in file_headers:
            path = header[4:].strip()
            if path == "/dev/null":
                errors.append(UNSUPPORTED_CREATE_DELETE)
            elif _is_unsafe_diff_path(path):
                errors.append(UNSAFE_PATH)

        if not any(line.startswith("@@") for line in block):
            errors.append(MISSING_HUNK_HEADER)

    return ValidationResult(ok=not errors, errors=_dedupe(errors), warnings=warnings)


def _is_unsafe_diff_path(path: str) -> bool:
    if path.startswith(("a/", "b/")):
        path = path[2:]
    pure = PurePosixPath(path)
    return pure.is_absolute() or ".." in pure.parts or ".git" in pure.parts


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
