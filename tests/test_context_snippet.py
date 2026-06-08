from pyfixagent.context.snippet import read_code_window, resolve_python_path


def test_resolve_python_path_rejects_workspace_escape_and_non_python(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "app.py").write_text("VALUE = 1\n", encoding="utf-8")
    outside = tmp_path / "outside.py"
    outside.write_text("SECRET = True\n", encoding="utf-8")
    (workspace / "notes.txt").write_text("nope", encoding="utf-8")

    assert resolve_python_path(workspace, "app.py") is not None
    assert resolve_python_path(workspace, str(outside)) is None
    assert resolve_python_path(workspace, "../outside.py") is None
    assert resolve_python_path(workspace, "notes.txt") is None


def test_read_code_window_around_target_line(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    lines = [f"line_{index}" for index in range(1, 11)]
    (workspace / "app.py").write_text("\n".join(lines), encoding="utf-8")

    start_line, end_line, content = read_code_window(workspace, "app.py", [5], line_window=2)

    assert start_line == 3
    assert end_line == 7
    assert content.splitlines() == ["line_3", "line_4", "line_5", "line_6", "line_7"]


def test_tests_files_can_be_included_but_optionally_excluded(tmp_path):
    workspace = tmp_path / "workspace"
    (workspace / "tests").mkdir(parents=True)
    (workspace / "tests" / "test_app.py").write_text("def test_app(): pass\n", encoding="utf-8")

    assert resolve_python_path(workspace, "tests/test_app.py", include_tests=True) is not None
    assert resolve_python_path(workspace, "tests/test_app.py", include_tests=False) is None
