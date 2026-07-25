from src.tokens.api import rotate_token


def test_rotation_follows_a_chain_to_the_current_token():
    assert rotate_token("old", {"old": "middle", "middle": "new"}) == "new"


def test_rotation_stops_when_token_is_current():
    assert rotate_token("current", {}) == "current"
