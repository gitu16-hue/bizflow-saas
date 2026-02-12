from datetime import datetime
import pytz

def combine_booking_datetime(date_str, time_str, timezone):
    """
    Converts booking date + time (string) into UTC datetime
    """
    tz = pytz.timezone(timezone)

    local_dt = datetime.strptime(
        f"{date_str} {time_str}",
        "%d %b %Y %I:%M %p"
    )

    localized = tz.localize(local_dt)
    return localized.astimezone(pytz.utc)
