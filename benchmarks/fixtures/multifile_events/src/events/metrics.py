def event_count_by_type(events):
    return {kind: sum(event.get("type") == kind for event in events) for kind in {event.get("type") for event in events}}
