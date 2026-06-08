import pytest

from pyfixagent.tools.replacement_tools import (
    ReplacementEdit,
    apply_replacements,
    parse_replacements,
)


def test_parse_replacements_parses_json_array():
    edits = parse_replacements(
        '[{"path": "src/app.py", "old": "return False", "new": "return True"}]'
    )

    assert edits == [ReplacementEdit(path="src/app.py", old="return False", new="return True")]


def test_parse_replacements_strips_json_code_fence():
    edits = parse_replacements(
        '```json\n[{"path": "src/app.py", "old": "return False", "new": "return True"}]\n```'
    )

    assert edits[0].path == "src/app.py"
    assert edits[0].old == "return False"


def test_parse_replacements_extracts_json_array_from_explanation():
    edits = parse_replacements(
        'Here is the replacement:\n[{"path": "src/app.py", "old": "return False", "new": "return True"}]\nDone.'
    )

    assert edits == [ReplacementEdit(path="src/app.py", old="return False", new="return True")]


def test_parse_replacements_rejects_invalid_json():
    with pytest.raises(ValueError, match="Invalid replacement JSON"):
        parse_replacements("[")


def test_parse_replacements_rejects_non_list():
    with pytest.raises(ValueError, match="must be a list"):
        parse_replacements('{"path": "src/app.py", "old": "x", "new": "y"}')


def test_parse_replacements_rejects_missing_fields():
    with pytest.raises(ValueError, match="missing fields: new"):
        parse_replacements('[{"path": "src/app.py", "old": "x"}]')


def test_parse_replacements_rejects_empty_old():
    with pytest.raises(ValueError, match="old must not be empty"):
        parse_replacements('[{"path": "src/app.py", "old": "", "new": "y"}]')


def test_parse_replacements_rejects_empty_path():
    with pytest.raises(ValueError, match="path must not be empty"):
        parse_replacements('[{"path": "", "old": "x", "new": "y"}]')


def test_apply_replacements_replaces_single_unique_old_text(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_text("def ok():\n    return False\n", encoding="utf-8")

    result = apply_replacements(
        workspace,
        [ReplacementEdit(path="app.py", old="return False", new="return True")],
    )

    assert result.success
    assert result.changed_files == ["app.py"]
    assert target.read_text(encoding="utf-8") == "def ok():\n    return True\n"


def test_apply_replacements_fails_when_old_is_missing_without_modifying_file(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    original = "def ok():\n    return False\n"
    target.write_text(original, encoding="utf-8")

    result = apply_replacements(
        workspace,
        [ReplacementEdit(path="app.py", old="return None", new="return True")],
    )

    assert not result.success
    assert "old text was not found" in (result.error or "")
    assert target.read_text(encoding="utf-8") == original


def test_apply_replacements_fails_when_old_appears_multiple_times_without_modifying_file(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    original = "def one():\n    return False\n\ndef two():\n    return False\n"
    target.write_text(original, encoding="utf-8")

    result = apply_replacements(
        workspace,
        [ReplacementEdit(path="app.py", old="return False", new="return True")],
    )

    assert not result.success
    assert "appears multiple times" in (result.error or "")
    assert target.read_text(encoding="utf-8") == original


def test_apply_replacements_uses_start_line_when_old_appears_multiple_times(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "app.py"
    target.write_text(
        "def one():\n    return False\n\n\ndef two():\n    return False\n",
        encoding="utf-8",
    )

    result = apply_replacements(
        workspace,
        [ReplacementEdit(path="app.py", old="return False", new="return True", start_line=6)],
    )

    assert result.success
    assert target.read_text(encoding="utf-8") == (
        "def one():\n    return False\n\n\ndef two():\n    return True\n"
    )


def test_parse_replacements_accepts_optional_start_line():
    edits = parse_replacements(
        '[{"path": "src/app.py", "old": "return False", "new": "return True", "start_line": 12}]'
    )

    assert edits == [ReplacementEdit(path="src/app.py", old="return False", new="return True", start_line=12)]


def test_apply_replacements_rejects_tests_directory(tmp_path):
    workspace = tmp_path / "workspace"
    target_dir = workspace / "tests"
    target_dir.mkdir(parents=True)
    target = target_dir / "test_app.py"
    target.write_text("def test_ok():\n    assert False\n", encoding="utf-8")

    result = apply_replacements(
        workspace,
        [ReplacementEdit(path="tests/test_app.py", old="assert False", new="assert True")],
    )

    assert not result.success
    assert "tests/" in (result.error or "")
    assert target.read_text(encoding="utf-8") == "def test_ok():\n    assert False\n"


def test_apply_replacements_rejects_path_traversal(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("value = False\n", encoding="utf-8")

    result = apply_replacements(
        workspace,
        [ReplacementEdit(path="../outside.py", old="False", new="True")],
    )

    assert not result.success
    assert "escapes workspace" in (result.error or "")
    assert outside.read_text(encoding="utf-8") == "value = False\n"


def test_apply_replacements_only_allows_py_files(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "notes.txt"
    target.write_text("value = False\n", encoding="utf-8")

    result = apply_replacements(
        workspace,
        [ReplacementEdit(path="notes.txt", old="False", new="True")],
    )

    assert not result.success
    assert ".py file" in (result.error or "")
    assert target.read_text(encoding="utf-8") == "value = False\n"
