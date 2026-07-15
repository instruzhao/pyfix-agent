from src.lookup import nested_get


def test_reads_dotted_nested_path():
    assert nested_get({"user": {"profile": {"name": "Ada"}}}, "user.profile.name") == "Ada"
