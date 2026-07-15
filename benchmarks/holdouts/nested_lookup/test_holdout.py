from src.lookup import nested_get


def test_returns_default_for_missing_path():
    data = {"user": {"profile": {"active": False}}}
    assert nested_get(data, "user.profile.active", True) is False
    assert nested_get(data, "user.profile.name", "unknown") == "unknown"
