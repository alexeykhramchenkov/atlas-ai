from datetime import date, datetime, time
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")

def moscow_date(value):
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        stamp = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=MOSCOW)
    return stamp.astimezone(MOSCOW).date()

def moscow_midnight(day):
    return datetime.combine(day, time.min, tzinfo=MOSCOW).isoformat()
