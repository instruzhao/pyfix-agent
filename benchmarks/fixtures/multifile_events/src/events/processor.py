from src.events.identity import event_id


def ordered_unique_events(events):
    return list({event_id(event): event for event in events}.values())
