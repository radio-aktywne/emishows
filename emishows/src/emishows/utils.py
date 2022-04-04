from datetime import datetime
from zoneinfo import ZoneInfo


def utczone() -> ZoneInfo:
    return ZoneInfo("Etc/UTC")


def utcnow() -> datetime:
    return datetime.now(utczone())


def parse_datetime_with_timezone(dt: str) -> datetime:
    parts = dt.split(" ")
    dt, tz = parts[0], (parts[1] if len(parts) > 1 else None)
    dt = datetime.fromisoformat(dt)
    if is_timezone_aware(dt):
        raise ValueError(
            "Datetime should be naive. Pass timezone name atfer space."
        )
    tz = ZoneInfo(tz) if tz else utczone()
    return dt.replace(tzinfo=tz)


def is_timezone_aware(dt: datetime) -> bool:
    return dt.tzinfo is not None and dt.tzinfo.utcoffset(dt) is not None
