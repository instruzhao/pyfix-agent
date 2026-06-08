import json

from patch_eval.types import (
    EMPTY_OUTPUT,
    JSON_PARSE_ERROR,
    MARKDOWN_FENCE_FOUND,
    NO_PATCH_FOUND,
    ParseResult,
)


def parse_agent_output(raw_model_output: str) -> ParseResult:
    if raw_model_output is None or not raw_model_output.strip():
        return ParseResult(cleaned_patch=None, source_type=None, errors=[EMPTY_OUTPUT])

    warnings: list[str] = []
    text = raw_model_output.strip()
    if "```" in text:
        warnings.append(MARKDOWN_FENCE_FOUND)
    text = _strip_outer_code_fence(text)

    json_candidates = [text]
    embedded_json = _extract_first_json_object(text)
    if embedded_json is not None and embedded_json != text:
        json_candidates.append(embedded_json)

    seen: set[str] = set()
    for candidate in json_candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            warnings.append(f"{JSON_PARSE_ERROR}: {exc}")
            continue

        if isinstance(data, dict):
            for field in ("patch", "cleaned_patch", "raw_model_output"):
                value = data.get(field)
                if isinstance(value, str) and value.strip():
                    cleaned = _extract_patch_from_text(value)
                    if cleaned:
                        return ParseResult(cleaned_patch=_with_newline(cleaned), source_type=f"json:{field}", warnings=warnings)

    cleaned = _extract_patch_from_text(text)
    if cleaned:
        return ParseResult(cleaned_patch=_with_newline(cleaned), source_type="diff", warnings=warnings)

    return ParseResult(cleaned_patch=None, source_type=None, errors=[NO_PATCH_FOUND], warnings=warnings)


def _strip_outer_code_fence(text: str) -> str:
    lines = text.strip().splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_first_json_object(text: str) -> str | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char != "{":
            continue
        try:
            _, end = decoder.raw_decode(text[index:])
        except json.JSONDecodeError:
            continue
        return text[index : index + end]
    return None


def _extract_patch_from_text(text: str) -> str | None:
    candidate = _strip_outer_code_fence(text.strip())
    candidate = _maybe_unescape_whole_patch(candidate)
    lines = candidate.splitlines()

    start_index = None
    for index, line in enumerate(lines):
        if line.startswith("diff --git ") or _is_traditional_header_start(lines, index):
            start_index = index
            break

    if start_index is None:
        return None

    patch_lines = _trim_trailing_non_patch_lines(lines[start_index:])
    return "\n".join(patch_lines).strip()


def _maybe_unescape_whole_patch(text: str) -> str:
    if "\n" not in text and "\\n" in text and ("diff --git " in text or "--- a/" in text):
        return text.replace("\\n", "\n").replace('\\"', '"')
    return text


def _is_traditional_header_start(lines: list[str], index: int) -> bool:
    return (
        lines[index].startswith("--- a/")
        and index + 1 < len(lines)
        and lines[index + 1].startswith("+++ b/")
    )


def _trim_trailing_non_patch_lines(lines: list[str]) -> list[str]:
    end_index = len(lines)
    while end_index > 0 and not _looks_like_patch_line(lines[end_index - 1]):
        end_index -= 1
    return lines[:end_index]


def _looks_like_patch_line(line: str) -> bool:
    return line.startswith(
        (
            "diff --git ",
            "index ",
            "new file mode ",
            "deleted file mode ",
            "old mode ",
            "new mode ",
            "similarity index ",
            "rename from ",
            "rename to ",
            "--- ",
            "+++ ",
            "@@",
            " ",
            "+",
            "-",
            "\\",
        )
    )


def _with_newline(text: str) -> str:
    return f"{text.rstrip()}\n" if text.strip() else ""
