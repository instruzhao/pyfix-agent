from pathlib import Path
import argparse
import subprocess


def run_command(command: list[str], cwd: Path) -> None:
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


def ensure_demo_path(project_root: Path, demo_path: Path) -> Path:
    resolved = demo_path.resolve()
    expected = (project_root / "workspaces" / "demo_project").resolve()
    if resolved != expected:
        raise RuntimeError(f"refusing to reset unexpected path: {resolved}")
    parts = resolved.parts
    if "workspaces" not in parts or resolved.name != "demo_project":
        raise RuntimeError(f"demo path safety check failed: {resolved}")
    if not (resolved / ".git").exists():
        raise RuntimeError(f"demo project is not a git repository: {resolved}")
    return resolved


def clean_output_dir(path: Path) -> None:
    if not path.exists():
        return
    for child in path.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            raise RuntimeError(f"refusing to recursively delete output directory: {child}")
        child.unlink()


def reset_demo(clean_outputs: bool = False) -> None:
    project_root = Path(__file__).resolve().parents[1]
    demo_path = ensure_demo_path(project_root, project_root / "workspaces" / "demo_project")

    run_command(["git", "reset", "--hard", "HEAD"], cwd=demo_path)
    run_command(["git", "clean", "-fd"], cwd=demo_path)

    if clean_outputs:
        clean_output_dir(project_root / "outputs" / "patches")
        clean_output_dir(project_root / "outputs" / "traces")

    print(f"Demo project reset: {demo_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Reset the demo project to its committed failing baseline.")
    parser.add_argument(
        "--clean-outputs",
        action="store_true",
        help="Also remove generated files under outputs/patches and outputs/traces, keeping .gitkeep files.",
    )
    args = parser.parse_args()
    reset_demo(clean_outputs=args.clean_outputs)


if __name__ == "__main__":
    main()
