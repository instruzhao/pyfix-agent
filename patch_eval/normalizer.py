from patch_eval.types import (
    MISSING_DIFF_GIT_HEADER_NORMALIZED,
    NormalizeResult,
    UNSUPPORTED_CREATE_DELETE,
)


def normalize_git_diff_headers(cleaned_patch: str) -> NormalizeResult:
    if cleaned_patch is None:
        return NormalizeResult(normalized_patch=None, errors=[])

    lines = cleaned_patch.strip().splitlines()
    output: list[str] = []
    warnings: list[str] = []
    index = 0
    active_diff_header: str | None = None

    while index < len(lines):
        line = lines[index]
        if line.startswith("diff --git "):
            active_diff_header = line
            output.append(line)
            index += 1
            continue

        if line.startswith("--- ") and index + 1 < len(lines) and lines[index + 1].startswith("+++ "):
            old_path = line.removeprefix("--- ").strip()
            new_path = lines[index + 1].removeprefix("+++ ").strip()
            if old_path == "/dev/null" or new_path == "/dev/null":
                return NormalizeResult(
                    normalized_patch=None,
                    errors=[UNSUPPORTED_CREATE_DELETE],
                    warnings=warnings,
                )

            expected = f"diff --git {old_path} {new_path}"
            if active_diff_header != expected:
                output.append(expected)
                warnings.append(MISSING_DIFF_GIT_HEADER_NORMALIZED)
            active_diff_header = expected
            output.append(line)
            output.append(lines[index + 1])
            index += 2
            continue

        output.append(line)
        index += 1

    normalized = "\n".join(output).strip()
    return NormalizeResult(
        normalized_patch=f"{normalized}\n" if normalized else "",
        warnings=warnings,
    )
