from src.flags.coercion import parse_bool


def resolve_flag(default, override=None):
    return parse_bool(override or default)
