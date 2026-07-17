from src.auth.api import can_access


def test_role_inheritance_is_transitive():
    assert can_access("manager", "viewer") is True


def test_unrelated_or_unknown_roles_are_denied():
    assert can_access("viewer", "editor") is False
    assert can_access("unknown", "viewer") is False
