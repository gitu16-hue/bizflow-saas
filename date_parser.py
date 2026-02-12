import dateparser
from datetime import datetime
import pytz

IST = pytz.timezone("Asia/Kolkata")


def parse_datetime(text: str):
    """
    Converts natural language date/time into datetime object (IST).
    Returns (date_str, time_str, datetime_obj) or (None, None, None)
    """

    settings = {
        "PREFER_DATES_FROM": "future",
        "TIMEZONE": "Asia/Kolkata",
        "RETURN_AS_TIMEZONE_AWARE": True,
    }

    dt = dateparser.parse(text, settings=settings)

    if not dt:
        return None, None, None

    dt = dt.astimezone(IST)

    date_str = dt.strftime("%d %b %Y")   # 15 Jan 2026
    time_str = dt.strftime("%I:%M %p")   # 06:00 PM

    return date_str, time_str, dt
