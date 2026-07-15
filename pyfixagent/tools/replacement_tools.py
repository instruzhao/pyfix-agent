from dataclasses import dataclass
import json
from pathlib import Path

from pyfixagent.tools.edit_policy import EditPolicy


@dataclass
class ReplacementResult:
    success: bool
    changed_files: list[str]
    error: str | None = None


@dataclass
class ReplacementEdit:
    path: str
    old: str
    new: str
    start_line: int | None = None


def parse_replacements(raw_output: str) -> list[ReplacementEdit]:
    text = _extract_json_array(_strip_code_fence(raw_output))
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid replacement JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("replacement JSON must be a list")

    edits: list[ReplacementEdit] = []
    for index, item in enumerate(data):
        if not isinstance(item, dict):
            raise ValueError(f"replacement item {index} must be an object")

        missing = [field for field in ("path", "old", "new") if field not in item]
        if missing:
            raise ValueError(f"replacement item {index} is missing fields: {', '.join(missing)}")

        for field in ("path", "old", "new"):
            if not isinstance(item[field], str):
                raise ValueError(f"replacement item {index} field {field} must be a string")

        if item["path"] == "":
            raise ValueError(f"replacement item {index} field path must not be empty")
        if item["old"] == "":
            raise ValueError(f"replacement item {index} field old must not be empty")
        if item["old"] == item["new"]:
            raise ValueError(f"replacement item {index} old and new must differ")

        start_line = item.get("start_line")
        if start_line is not None:
            if not isinstance(start_line, int) or start_line < 1:
                raise ValueError(f"replacement item {index} field start_line must be a positive integer")

        edits.append(ReplacementEdit(path=item["path"], old=item["old"], new=item["new"], start_line=start_line))

    return edits


def apply_replacements(
    workspace: str | Path,
    edits: list[ReplacementEdit],
    policy: EditPolicy | None = None,
) -> ReplacementResult:
    workspace_path = Path(workspace).resolve()
    active_policy = policy or EditPolicy()
    policy_error = active_policy.validate_paths([edit.path for edit in edits])
    if policy_error:
        return ReplacementResult(success=False, changed_files=[], error=policy_error)
    changed_lines = sum(max(len(edit.old.splitlines()), len(edit.new.splitlines())) for edit in edits)
    policy_error = active_policy.validate_changed_lines(changed_lines)
    if policy_error:
        return ReplacementResult(success=False, changed_files=[], error=policy_error)
    planned_changes: dict[Path, str] = {}
    originals: dict[Path, str] = {}
    changed_files: list[str] = []

    for edit in edits:
        try:
            target = _resolve_target(workspace_path, edit.path)
        except ValueError as exc:
            return ReplacementResult(success=False, changed_files=[], error=str(exc))

        rel = target.relative_to(workspace_path).as_posix()

        if target not in originals:
            try:
                originals[target] = target.read_text(encoding="utf-8")
            except Exception as exc:
                return ReplacementResult(
                    success=False,
                    changed_files=[],
                    error=f"failed to read replacement target {edit.path}: {exc}",
                )

        current = planned_changes.get(target, originals[target])
        matches = _find_occurrences(current, edit.old)
        if not matches:
            return ReplacementResult(
                success=False,
                changed_files=[],
                error=f"old text was not found exactly once in {edit.path}",
            )
        if len(matches) > 1 and edit.start_line is None:
            return ReplacementResult(
                success=False,
                changed_files=[],
                error=(
                    f"old text appears multiple times in {edit.path}; provide a more precise old fragment "
                    "or include start_line"
                ),
            )

        match_index = matches[0] if len(matches) == 1 else _nearest_match_by_line(current, matches, edit.start_line)
        if match_index is None:
            return ReplacementResult(
                success=False,
                changed_files=[],
                error=f"old text appears multiple times in {edit.path}; start_line was ambiguous",
            )

        planned_changes[target] = current[:match_index] + edit.new + current[match_index + len(edit.old) :]
        if rel not in changed_files:
            changed_files.append(rel)

    try:
        for target, content in planned_changes.items():
            target.write_text(content, encoding="utf-8", newline="\n")
            _remove_python_bytecode_cache(target)
    except Exception as exc:
        return ReplacementResult(success=False, changed_files=[], error=f"failed to write replacements: {exc}")

    return ReplacementResult(success=True, changed_files=changed_files)


def _strip_code_fence(raw_output: str) -> str:
    text = raw_output.strip()
    lines = text.splitlines()
    if lines and lines[0].strip().startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _extract_json_array(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped

    start = stripped.find("[")
    end = stripped.rfind("]")
    if start != -1 and end != -1 and end > start:
        return stripped[start : end + 1].strip()
    return stripped


def _find_occurrences(text: str, needle: str) -> list[int]:
    matches: list[int] = []
    start = 0
    while True:
        index = text.find(needle, start)
        if index == -1:
            return matches
        matches.append(index)
        start = index + max(1, len(needle))


def _nearest_match_by_line(text: str, matches: list[int], start_line: int | None) -> int | None:
    if start_line is None:
        return None

    line_matches = [(match, text.count("\n", 0, match) + 1) for match in matches]
    distances = [(match, abs(line - start_line)) for match, line in line_matches]
    best_distance = min(distance for _, distance in distances)
    best_matches = [match for match, distance in distances if distance == best_distance]
    if len(best_matches) != 1:
        return None
    return best_matches[0]


def _resolve_target(workspace: Path, raw_path: str) -> Path:
    relative_path = Path(raw_path)
    if relative_path.is_absolute():
        raise ValueError(f"replacement path must be relative to workspace: {raw_path}")

    target = (workspace / relative_path).resolve()
    try:
        target.relative_to(workspace)
    except ValueError as exc:
        raise ValueError(f"replacement path escapes workspace: {raw_path}") from exc
    return target


def _remove_python_bytecode_cache(source_path: Path) -> None:
    cache_dir = source_path.parent / "__pycache__"
    if not cache_dir.exists():
        return

    for pyc_path in cache_dir.glob(f"{source_path.stem}.*.pyc"):
        pyc_path.unlink()
