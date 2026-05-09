from datetime import datetime


def get_current_utc():

    return datetime.utcnow()


def convert_to_iso(
    dt: datetime
):

    return dt.isoformat()


def parse_iso_datetime(
    value: str
):

    return datetime.fromisoformat(value)