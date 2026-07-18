from pathlib import Path
import shutil
import subprocess

from scripts.reset_demo import clean_outputs, reset_workspace


def test_reset_workspace_restores_demo_baseline_and_cleans_runtime_artifacts(tmp_path):
    source_root = Path(__file__).resolve().parents[1]
    repo = tmp_path / "repo"
    shutil.copytree(source_root / "workspaces", repo / "workspaces")
    subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
    subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "baseline"],
        cwd=repo,
        check=True,
        capture_output=True,
    )

    billing_path = repo / "workspaces" / "demo_project" / "src" / "billing.py"
    billing_path.write_text("def calculate_order_total(*args, **kwargs):\n    return None\n", encoding="utf-8")
    pycache = repo / "workspaces" / "demo_project" / "src" / "__pycache__"
    pycache.mkdir(exist_ok=True)
    (pycache / "billing.pyc").write_text("cache", encoding="utf-8")

    reset_path = reset_workspace(repo, "demo")

    assert reset_path == (repo / "workspaces" / "demo_project").resolve()
    assert "subtotal = sum(item.unit_price * item.quantity for item in items)" in billing_path.read_text(
        encoding="utf-8"
    )
    assert not pycache.exists()


def test_clean_outputs_keeps_gitkeep_and_removes_generated_files(tmp_path):
    patches = tmp_path / "outputs" / "patches"
    traces = tmp_path / "outputs" / "traces"
    patches.mkdir(parents=True)
    traces.mkdir(parents=True)
    (patches / ".gitkeep").write_text("\n", encoding="utf-8")
    (patches / "run.patch").write_text("patch", encoding="utf-8")
    (traces / ".gitkeep").write_text("\n", encoding="utf-8")
    (traces / "run.json").write_text("{}", encoding="utf-8")

    clean_outputs(tmp_path)

    assert (patches / ".gitkeep").exists()
    assert (traces / ".gitkeep").exists()
    assert not (patches / "run.patch").exists()
    assert not (traces / "run.json").exists()
