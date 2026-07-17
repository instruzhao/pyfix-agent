def event_id(event):
    if "id" not in event:
        raise ValueError("event id is required")
    return event["id"]
