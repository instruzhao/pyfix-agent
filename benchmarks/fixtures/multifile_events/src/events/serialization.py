def serialize_event(event):
    return ",".join(f"{key}={event[key]}" for key in sorted(event))
