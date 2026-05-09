from datetime import datetime


def build_case_timeline(events: list):

    sorted_events = sorted(
        events,
        key=lambda x: x["timestamp"]
    )

    return sorted_events


def detect_timeline_conflicts(events: list):

    conflicts = []

    for i in range(len(events) - 1):

        current_event = events[i]
        next_event = events[i + 1]

        current_time = datetime.fromisoformat(
            current_event["timestamp"]
        )

        next_time = datetime.fromisoformat(
            next_event["timestamp"]
        )

        if current_time > next_time:
            conflicts.append({
                "event_1": current_event,
                "event_2": next_event
            })

    return conflicts