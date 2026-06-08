from pyfixagent.sandbox.local_sandbox import LocalSandbox


def test_sandbox_allows_python_command(tmp_path):
    sandbox = LocalSandbox(tmp_path)

    result = sandbox.run(["python", "-c", "print('hello')"])

    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_sandbox_disables_python_bytecode_cache(tmp_path):
    sandbox = LocalSandbox(tmp_path)

    result = sandbox.run(
        ["python", "-c", "import os; print(os.environ.get('PYTHONDONTWRITEBYTECODE'))"]
    )

    assert result.exit_code == 0
    assert result.stdout.strip() == "1"


def test_sandbox_removes_stale_python_bytecode_cache_before_python_command(tmp_path):
    cache_dir = tmp_path / "__pycache__"
    cache_dir.mkdir()
    pyc_path = cache_dir / "sample.cpython-311.pyc"
    pyc_path.write_bytes(b"stale bytecode")
    sandbox = LocalSandbox(tmp_path)

    result = sandbox.run(["python", "-c", "print('ok')"])

    assert result.exit_code == 0
    assert not pyc_path.exists()


def test_sandbox_blocks_dangerous_command(tmp_path):
    sandbox = LocalSandbox(tmp_path)

    result = sandbox.run(["rm", "-rf", "."])

    assert result.exit_code == 126
    assert "dangerous" in result.stderr


def test_sandbox_runs_pytest(tmp_path):
    (tmp_path / "test_sample.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    sandbox = LocalSandbox(tmp_path)

    result = sandbox.run(["python", "-m", "pytest"])

    assert result.exit_code == 0
    assert "1 passed" in result.stdout
