from pathlib import Path
import argparse
import shutil
import subprocess


WORKSPACES = {
    "demo": Path("workspaces/demo_project"),
    "sklearn": Path("workspaces/sklearn_iris_tree_project"),
}


def run_command(command: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        timeout=30,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed: {' '.join(command)}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}"
        )
    return completed


def reset_workspace(project_root: Path, workspace: str) -> Path:
    if workspace not in WORKSPACES:
        raise ValueError(f"unknown workspace: {workspace}")

    relative = WORKSPACES[workspace]
    target = (project_root / relative).resolve()
    _ensure_inside_project(project_root, target)
    if not target.exists():
        raise RuntimeError(f"workspace does not exist: {target}")
    if (target / ".git").exists():
        raise RuntimeError(f"nested git repository is not allowed in workspace: {target}")

    run_command(["git", "restore", "--source", "HEAD", "--", relative.as_posix()], cwd=project_root)
    run_command(["git", "clean", "-fd", "--", relative.as_posix()], cwd=project_root)
    clean_workspace_runtime_artifacts(target)
    return target


def clean_workspace_runtime_artifacts(workspace_path: Path) -> None:
    for name in (".pytest_tmp", ".pytest_cache", "__pycache__"):
        for path in _find_named_paths(workspace_path, name):
            _remove_path(path, workspace_path)


def clean_outputs(project_root: Path) -> None:
    for relative in (Path("outputs/patches"), Path("outputs/traces")):
        output_dir = project_root / relative
        if not output_dir.exists():
            continue
        _ensure_inside_project(project_root, output_dir.resolve())
        for child in output_dir.iterdir():
            if child.name == ".gitkeep":
                continue
            _remove_path(child, output_dir)


def reset_demo(workspace: str = "demo", clean_outputs_requested: bool = False, all_workspaces: bool = False) -> list[Path]:
    project_root = Path(__file__).resolve().parents[1]
    selected = list(WORKSPACES) if all_workspaces else [workspace]
    reset_paths = [reset_workspace(project_root, item) for item in selected]

    if clean_outputs_requested:
        clean_outputs(project_root)

    for path in reset_paths:
        print(f"Workspace reset to failing baseline: {path}")
    return reset_paths


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset example workspaces to their committed failing baselines.")
    parser.add_argument(
        "--workspace",
        choices=sorted(WORKSPACES),
        default="demo",
        help="Example workspace to reset when --all is not used. Defaults to demo.",
    )
    parser.add_argument("--all", action="store_true", help="Reset all example workspaces.")
    parser.add_argument(
        "--clean-outputs",
        action="store_true",
        help="Also remove generated files under outputs/patches and outputs/traces, keeping .gitkeep files.",
    )
    args = parser.parse_args()
    reset_demo(
        workspace=args.workspace,
        clean_outputs_requested=args.clean_outputs,
        all_workspaces=args.all,
    )


def _find_named_paths(root: Path, name: str) -> list[Path]:
    result: list[Path] = []
    if root.name == name:
        result.append(root)
    result.extend(path for path in root.rglob(name))
    return result


def _remove_path(path: Path, safety_root: Path) -> None:
    resolved = path.resolve()
    _ensure_inside_project(safety_root, resolved)
    if resolved.is_dir():
        shutil.rmtree(resolved)
    elif resolved.exists():
        resolved.unlink()


def _ensure_inside_project(project_root: Path, target: Path) -> None:
    try:
        target.relative_to(project_root.resolve())
    except ValueError as exc:
        raise RuntimeError(f"refusing to touch path outside project: {target}") from exc


if __name__ == "__main__":
    main()
