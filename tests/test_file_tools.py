from pyfixagent.tools.file_tools import list_files, read_python_files


def test_list_files_ignores_cache_dirs(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text("print('ok')\n", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "app.pyc").write_text("cache", encoding="utf-8")

    tree = list_files(tmp_path)

    assert "src/" in tree
    assert "src/app.py" in tree
    assert "__pycache__" not in tree


def test_read_python_files_includes_separators_and_ignores_git(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "ignored.py").write_text("bad = True\n", encoding="utf-8")

    content = read_python_files(tmp_path)

    assert "--- pkg/mod.py ---" in content
    assert "VALUE = 1" in content
    assert "ignored.py" not in content
