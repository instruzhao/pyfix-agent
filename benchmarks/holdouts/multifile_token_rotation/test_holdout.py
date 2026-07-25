import pytest

from src.tokens.api import rotate_token


def test_rotation_follows_a_chain_to_the_final_token():
    assert rotate_token("v1", {"v1": "v2", "v2": "v3"}) == "v3"


def test_rotation_rejects_cycles_instead_of_looping():
    with pytest.raises(ValueError, match="cycle"):
        rotate_token("v1", {"v1": "v2", "v2": "v1"})
