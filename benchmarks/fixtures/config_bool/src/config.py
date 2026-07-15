def parse_bool(value):
    if isinstance(value, bool):
        return value
    return bool(value)
