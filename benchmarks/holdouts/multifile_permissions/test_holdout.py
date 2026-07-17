from src.auth.api import can_access


def test_deeper_admin_inheritance():
    assert can_access("admin", "viewer") is True


def test_direct_and_same_role_access():
    assert can_access("editor", "viewer") is True
    assert can_access("editor", "editor") is True
