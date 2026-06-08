from pathlib import Path

from patch_eval.git_apply import run_git_apply_check
from patch_eval.normalizer import normalize_git_diff_headers
from patch_eval.parser import parse_agent_output
from patch_eval.types import EvaluationResult
from patch_eval.validator import validate_patch_format


def evaluate_agent_output(repo_path: Path, raw_model_output: str) -> EvaluationResult:
    errors: list[str] = []
    warnings: list[str] = []

    parse_result = parse_agent_output(raw_model_output)
    errors.extend(parse_result.errors)
    warnings.extend(parse_result.warnings)
    if parse_result.cleaned_patch is None or parse_result.errors:
        return EvaluationResult(
            ok=False,
            cleaned_patch=parse_result.cleaned_patch,
            normalized_patch=None,
            errors=_dedupe(errors),
            warnings=_dedupe(warnings),
            error_type=errors[0] if errors else None,
        )

    normalize_result = normalize_git_diff_headers(parse_result.cleaned_patch)
    errors.extend(normalize_result.errors)
    warnings.extend(normalize_result.warnings)
    if normalize_result.normalized_patch is None or normalize_result.errors:
        return EvaluationResult(
            ok=False,
            cleaned_patch=parse_result.cleaned_patch,
            normalized_patch=normalize_result.normalized_patch,
            errors=_dedupe(errors),
            warnings=_dedupe(warnings),
            error_type=errors[0] if errors else None,
        )

    validation_result = validate_patch_format(normalize_result.normalized_patch)
    errors.extend(validation_result.errors)
    warnings.extend(validation_result.warnings)
    if not validation_result.ok:
        return EvaluationResult(
            ok=False,
            cleaned_patch=parse_result.cleaned_patch,
            normalized_patch=normalize_result.normalized_patch,
            errors=_dedupe(errors),
            warnings=_dedupe(warnings),
            error_type=validation_result.errors[0] if validation_result.errors else None,
        )

    git_result = run_git_apply_check(repo_path, normalize_result.normalized_patch)
    if not git_result.ok:
        errors.append(git_result.error_type or "GIT_APPLY_CHECK_FAILED")

    return EvaluationResult(
        ok=git_result.ok,
        cleaned_patch=parse_result.cleaned_patch,
        normalized_patch=normalize_result.normalized_patch,
        errors=_dedupe(errors),
        warnings=_dedupe(warnings),
        error_type=git_result.error_type,
        git_apply_stdout=git_result.stdout,
        git_apply_stderr=git_result.stderr,
        git_apply_command=git_result.command,
    )


def _dedupe(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
