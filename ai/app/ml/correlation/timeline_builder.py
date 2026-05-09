from datetime import datetime


def build_timeline(events: list):

    sorted_events = sorted(
        events,
        key=lambda event:
            datetime.fromisoformat(
                event["timestamp"]
            )
    )

    return sorted_events