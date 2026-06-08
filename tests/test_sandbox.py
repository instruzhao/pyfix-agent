from pyfixagent.sandbox.local_sandbox import LocalSandbox


def test_sandbox_allows_python_command(tmp_path):
    sandbox = LocalSandbox(tmp_path)

    result = sandbox.run(["python", "-c", "print('hello')"])

    assert result.exit_code == 0
    assert "hello" in result.stdout


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
