from datetime import datetime


def detect_timeline_anomalies(events: list):

    anomalies = []

    sorted_events = sorted(
        events,
        key=lambda event:
            datetime.fromisoformat(
                event["timestamp"]
            )
    )

    for i in range(
        len(sorted_events) - 1
    ):

        current_event = sorted_events[i]

        next_event = sorted_events[i + 1]

        current_time = datetime.fromisoformat(
            current_event["timestamp"]
        )

        next_time = datetime.fromisoformat(
            next_event["timestamp"]
        )

        if current_time > next_time:

            anomalies.append({
                "type": "TIMELINE_INCONSISTENCY",
                "event_1": current_event,
                "event_2": next_event
            })

    return anomalies