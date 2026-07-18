from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from pathlib import Path
import sys

from pyfixagent.tools.edit_policy import EditPolicy, changed_lines_from_patch, paths_from_patch
from pyfixagent.tools.patch_tools import apply_patch, check_patch, clean_patch_text
from pyfixagent.workspace import clean_workspace_error, inspect_workspace


@dataclass(frozen=True)
class PatchApproval:
    workspace: Path
    patch_path: Path
    digest: str
    modified_files: tuple[str, ...]
    changed_lines: int
    cleaned_patch: str


def inspect_exported_patch(
    workspace: Path,
    patch_path: Path,
    *,
    allowed_paths: tuple[str, ...] = (),
    max_changed_files: int = 8,
    max_changed_lines: int = 400,
) -> PatchApproval:
    workspace = Path(workspace).resolve()
    patch_path = Path(patch_path).resolve()
    state = inspect_workspace(workspace)
    workspace_error = clean_workspace_error(state)
    if workspace_error:
        raise ValueError(workspace_error)
    try:
        raw_patch = patch_path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise ValueError(f"patch file does not exist: {patch_path}") from exc
    except (OSError, UnicodeError) as exc:
        raise ValueError(f"failed to read UTF-8 patch file {patch_path}: {exc}") from exc

    cleaned = clean_patch_text(raw_patch)
    policy = EditPolicy(
        allowed_paths=allowed_paths,
        max_files=max(1, int(max_changed_files)),
        max_changed_lines=max(1, int(max_changed_lines)),
    )
    checked = check_patch(workspace, cleaned, policy=policy)
    if not checked.success:
        raise ValueError(checked.error or checked.stderr or "patch validation failed")
    digest = hashlib.sha256(cleaned.encode("utf-8")).hexdigest()
    return PatchApproval(
        workspace=workspace,
        patch_path=patch_path,
        digest=digest,
        modified_files=tuple(paths_from_patch(cleaned)),
        changed_lines=changed_lines_from_patch(cleaned),
        cleaned_patch=cleaned,
    )


def apply_approved_patch(
    approval: PatchApproval,
    supplied_digest: str,
    *,
    allowed_paths: tuple[str, ...] = (),
    max_changed_files: int = 8,
    max_changed_lines: int = 400,
) -> None:
    if supplied_digest.strip().lower() != approval.digest:
        raise ValueError("approval digest does not match the validated patch")
    state = inspect_workspace(approval.workspace)
    workspace_error = clean_workspace_error(state)
    if workspace_error:
        raise ValueError(f"workspace changed after preview: {workspace_error}")
    policy = EditPolicy(
        allowed_paths=allowed_paths,
        max_files=max(1, int(max_changed_files)),
        max_changed_lines=max(1, int(max_changed_lines)),
    )
    result = apply_patch(approval.workspace, approval.cleaned_patch, policy=policy)
    if not result.success:
        raise ValueError(result.error or result.stderr or "failed to apply approved patch")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate an exported PyFixAgent patch and require digest-bound approval before applying it."
    )
    parser.add_argument("--workspace", required=True, type=Path, help="Clean Git workspace to update.")
    parser.add_argument("--patch", required=True, type=Path, help="Exported patch file to inspect.")
    parser.add_argument(
        "--approve",
        help="Exact SHA-256 printed by the preview step. Without it, no files are changed.",
    )
    parser.add_argument("--allowed-path", action="append", dest="allowed_paths")
    parser.add_argument("--max-changed-files", type=int, default=8)
    parser.add_argument("--max-changed-lines", type=int, default=400)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    allowed_paths = tuple(args.allowed_paths or ())
    try:
        approval = inspect_exported_patch(
            args.workspace,
            args.patch,
            allowed_paths=allowed_paths,
            max_changed_files=args.max_changed_files,
            max_changed_lines=args.max_changed_lines,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print("PyFixAgent patch approval")
    print(f"Workspace: {approval.workspace}")
    print(f"Patch: {approval.patch_path}")
    print(f"SHA-256: {approval.digest}")
    print(f"Modified files: {', '.join(approval.modified_files) or '(none)'}")
    print(f"Changed lines: {approval.changed_lines}")
    if not args.approve:
        print("Approval required: inspect the patch, then rerun with --approve <SHA-256>.")
        return 2
    try:
        apply_approved_patch(
            approval,
            args.approve,
            allowed_paths=allowed_paths,
            max_changed_files=args.max_changed_files,
            max_changed_lines=args.max_changed_lines,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print("Patch applied to the selected workspace. Changes remain uncommitted.")
    return 0


def cli() -> None:
    raise SystemExit(main())


if __name__ == "__main__":
    cli()
