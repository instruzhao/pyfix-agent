from src.tokens.registry import resolve_replacement


def rotate(current, replacements):
    return resolve_replacement(current, replacements)
