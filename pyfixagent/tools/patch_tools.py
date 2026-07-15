from dataclasses import dataclass
import json
from pathlib import Path
import subprocess

from pyfixagent.tools.edit_policy import EditPolicy, changed_lines_from_patch, paths_from_patch


@dataclass
class PatchApplyResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    error: str | None = None


@dataclass
class ValidationResult:
    success: bool
    error_code: str | None = None
    error: str | None = None


def clean_patch_text(patch_text: str) -> str:
    extracted = clean_model_output(patch_text)
    normalized = normalize_git_diff_headers(extracted)
    return _ensure_trailing_newline(normalized)


def clean_model_output(raw_model_output: str) -> str:
    text = _strip_outer_code_fence(raw_model_output.strip())

    json_text = _extract_first_json_object(text)
    if json_text is not None:
        try:
            data = json.loads(json_text)
        except json.JSONDecodeError:
            pass
        else:
            if isinstance(data, dict):
                for field in ("patch", "cleaned_patch", "raw_model_output"):
                    value = data.get(field)
                    if isinstance(value, str) and value.strip():
                        return _extract_patch_text(value)

    return _extract_patch_text(text)


def normalize_git_diff_headers(patch: str) -> str:
    lines = patch.strip().splitlines()
    output: list[str] = []
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
                output.append(line)
                output.append(lines[index + 1])
                index += 2
                continue

            expected = f"diff --git {old_path} {new_path}"
            if active_diff_header != expected:
                output.append(expected)
            active_diff_header = expected
            output.append(line)
            output.append(lines[index + 1])
            index += 2
            continue

        output.append(line)
        index += 1

    return "\n".join(output).strip()


def validate_patch_format(patch: str) -> ValidationResult:
    text = patch.strip()
    if not text:
        return ValidationResult(False, "EMPTY_OUTPUT", "patch is empty")
    if "```" in text:
        return ValidationResult(False, "MARKDOWN_FENCE_FOUND", "patch still contains Markdown code fence")
    if _has_natural_language_prefix(text):
        return ValidationResult(False, "NO_PATCH_FOUND", "patch appears to contain natural-language prefix")
    if "/dev/null" in text:
        return ValidationResult(False, "UNSUPPORTED_CREATE_DELETE", "create/delete patches are not supported")

    normalized = normalize_git_diff_headers(text)
    if "diff --git " not in normalized:
        return ValidationResult(False, "MISSING_DIFF_GIT_HEADER", "patch does not contain diff --git header")

    lines = normalized.splitlines()
    diff_indexes = [index for index, line in enumerate(lines) if line.startswith("diff --git ")]
    for block_number, start in enumerate(diff_indexes):
        end = diff_indexes[block_number + 1] if block_number + 1 < len(diff_indexes) else len(lines)
        block = lines[start:end]
        header_parts = block[0].split()
        if len(header_parts) < 4:
            return ValidationResult(False, "MISSING_DIFF_GIT_HEADER", f"invalid diff --git header: {block[0]}")

        for path in header_parts[2:4]:
            unsafe = _validate_diff_path(path)
            if unsafe:
                return unsafe

        if not any(line.startswith("--- ") for line in block) or not any(line.startswith("+++ ") for line in block):
            return ValidationResult(False, "MISSING_FILE_HEADER", f"missing ---/+++ file header after {block[0]}")
        if not any(line.startswith("@@") for line in block):
            return ValidationResult(False, "MISSING_HUNK_HEADER", f"missing hunk header after {block[0]}")

        for line in block:
            if line.startswith(("--- ", "+++ ")):
                path = line[4:].strip()
                if path == "/dev/null":
                    return ValidationResult(
                        False,
                        "UNSUPPORTED_CREATE_DELETE",
                        "create/delete patches are not supported",
                    )
                unsafe = _validate_diff_path(path)
                if unsafe:
                    return unsafe

    return ValidationResult(True)


def _extract_patch_text(text: str) -> str:
    text = _strip_outer_code_fence(text.strip())
    lines = text.splitlines()

    start_index = None
    for index, line in enumerate(lines):
        if line.startswith("diff --git ") or line.startswith("--- a/"):
            start_index = index
            break

    if start_index is None:
        return "\n".join(lines).strip() if lines else ""

    patch_lines = _trim_trailing_non_patch_lines(lines[start_index:])
    cleaned = "\n".join(patch_lines).strip()
    return cleaned


def save_patch(workspace: Path, patch_text: str, output_path: Path) -> Path:
    try:
        Path(workspace).resolve()
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        cleaned = clean_patch_text(patch_text)
        output_path.write_text(cleaned, encoding="utf-8", newline="\n")
        return output_path
    except Exception as exc:
        raise RuntimeError(f"failed to save patch to {output_path}: {exc}") from exc


def check_patch(
    workspace: Path,
    patch_text: str,
    timeout: int = 30,
    policy: EditPolicy | None = None,
) -> PatchApplyResult:
    workspace = Path(workspace)
    try:
        cleaned = clean_patch_text(patch_text)
        validation = validate_patch_format(cleaned)
        if not validation.success:
            return PatchApplyResult(success=False, error=f"{validation.error_code}: {validation.error}")
        policy_error = _validate_edit_policy(cleaned, policy)
        if policy_error:
            return PatchApplyResult(success=False, error=f"EDIT_POLICY_REJECTED: {policy_error}")

        completed = _run_git_apply(workspace, cleaned, ["git", "apply", "--check", "-"], timeout)
        success = completed.returncode == 0
        stderr = completed.stderr.decode("utf-8", errors="replace")
        return PatchApplyResult(
            success=success,
            stdout=completed.stdout.decode("utf-8", errors="replace"),
            stderr=stderr,
            error=None if success else f"GIT_APPLY_CHECK_FAILED: {stderr or 'git apply failed'}",
        )
    except subprocess.TimeoutExpired as exc:
        return PatchApplyResult(success=False, error=f"git apply --check timed out after {timeout}s: {exc}")
    except Exception as exc:
        return PatchApplyResult(success=False, error=f"failed to check patch: {exc}")


def apply_patch(
    workspace: Path,
    patch_text: str,
    timeout: int = 30,
    policy: EditPolicy | None = None,
) -> PatchApplyResult:
    workspace = Path(workspace)
    try:
        cleaned = clean_patch_text(patch_text)
        validation = validate_patch_format(cleaned)
        if not validation.success:
            return PatchApplyResult(success=False, error=f"{validation.error_code}: {validation.error}")
        policy_error = _validate_edit_policy(cleaned, policy)
        if policy_error:
            return PatchApplyResult(success=False, error=f"EDIT_POLICY_REJECTED: {policy_error}")

        completed = _run_git_apply(workspace, cleaned, ["git", "apply", "-"], timeout)
        success = completed.returncode == 0
        return PatchApplyResult(
            success=success,
            stdout=completed.stdout.decode("utf-8", errors="replace"),
            stderr=completed.stderr.decode("utf-8", errors="replace"),
            error=None if success else completed.stderr.decode("utf-8", errors="replace") or "git apply failed",
        )
    except subprocess.TimeoutExpired as exc:
        return PatchApplyResult(success=False, error=f"git apply timed out after {timeout}s: {exc}")
    except Exception as exc:
        return PatchApplyResult(success=False, error=f"failed to apply patch: {exc}")


def get_git_diff(workspace: Path, timeout: int = 30) -> PatchApplyResult:
    workspace = Path(workspace)
    try:
        completed = subprocess.run(
            ["git", "diff", "--", "."],
            cwd=workspace,
            timeout=timeout,
            capture_output=True,
            check=False,
        )
        success = completed.returncode == 0
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        return PatchApplyResult(
            success=success,
            stdout=stdout,
            stderr=stderr,
            error=None if success else f"GIT_DIFF_FAILED: {stderr or 'git diff failed'}",
        )
    except subprocess.TimeoutExpired as exc:
        return PatchApplyResult(success=False, error=f"GIT_DIFF_FAILED: git diff timed out after {timeout}s: {exc}")
    except Exception as exc:
        return PatchApplyResult(success=False, error=f"GIT_DIFF_FAILED: failed to run git diff: {exc}")


def _run_git_apply(
    workspace: Path,
    patch_text: str,
    command: list[str],
    timeout: int,
) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        command,
        input=patch_text.encode("utf-8"),
        cwd=workspace,
        timeout=timeout,
        capture_output=True,
        check=False,
    )


def _validate_edit_policy(patch: str, policy: EditPolicy | None) -> str | None:
    if policy is None:
        return None
    error = policy.validate_paths(paths_from_patch(patch))
    if error:
        return error
    return policy.validate_changed_lines(changed_lines_from_patch(patch))


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


def _previous_nonempty_line(lines: list[str]) -> str | None:
    for line in reversed(lines):
        if line.strip():
            return line
    return None


def _ensure_trailing_newline(text: str) -> str:
    stripped = text.strip()
    return f"{stripped}\n" if stripped else ""


def _has_natural_language_prefix(text: str) -> bool:
    first_line = text.splitlines()[0].strip().lower()
    natural_prefixes = (
        "here is the patch",
        "here's the patch",
        "below is the patch",
        "the patch is",
        "下面是补丁",
    )
    return any(first_line.startswith(prefix) for prefix in natural_prefixes)


def _validate_diff_path(path: str) -> ValidationResult | None:
    if path == "/dev/null":
        return ValidationResult(False, "UNSUPPORTED_CREATE_DELETE", "create/delete patches are not supported")

    if path.startswith(("a/", "b/")):
        relative = path[2:]
    else:
        relative = path

    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or ".git" in candidate.parts:
        return ValidationResult(False, "UNSAFE_PATH", f"unsafe patch path: {path}")
    return None


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
