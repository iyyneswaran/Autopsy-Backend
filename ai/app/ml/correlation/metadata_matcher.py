from datetime import datetime


def match_metadata_sources(data: dict):

    cctv_timestamp = data.get(
        "cctv_timestamp"
    )

    gps_timestamp = data.get(
        "gps_timestamp"
    )

    mobile_timestamp = data.get(
        "mobile_timestamp"
    )

    timestamps = [
        cctv_timestamp,
        gps_timestamp,
        mobile_timestamp
    ]

    parsed = [
        datetime.fromisoformat(ts)
        for ts in timestamps
        if ts
    ]

    min_time = min(parsed)

    max_time = max(parsed)

    difference = (
        max_time - min_time
    ).total_seconds()

    return {
        "matched": difference <= 300,
        "time_difference_seconds":
            difference
    }