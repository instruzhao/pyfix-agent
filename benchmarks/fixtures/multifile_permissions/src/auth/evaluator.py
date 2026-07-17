from src.auth.hierarchy import ROLE_PARENTS


def is_allowed(role, required_role):
    return role == required_role or required_role in ROLE_PARENTS.get(role, ())
