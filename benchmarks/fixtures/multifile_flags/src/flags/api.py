from src.flags.resolver import resolve_flag


def flag_value(default, override=None):
    return resolve_flag(default, override)
