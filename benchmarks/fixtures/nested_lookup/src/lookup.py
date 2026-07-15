def nested_get(data, dotted_path, default=None):
    current = data
    for part in dotted_path.split("/"):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current
