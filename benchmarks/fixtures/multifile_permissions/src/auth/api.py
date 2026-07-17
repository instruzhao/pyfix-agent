from src.auth.evaluator import is_allowed


def can_access(role, required_role):
    return is_allowed(role, required_role)
