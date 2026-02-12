from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta

SCOPES = ["https://www.googleapis.com/auth/calendar"]
SERVICE_ACCOUNT_FILE = "google_calendar.json"
CALENDAR_ID = "primary"  # or your specific calendar ID


def create_calendar_event(
    name: str,
    phone: str,
    date_str: str,
    time_str: str,
):
    creds = service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_FILE, scopes=SCOPES
    )

    service = build("calendar", "v3", credentials=creds)

    # TEMP SIMPLE PARSING (we’ll improve later)
    start_time = datetime.now().replace(hour=18, minute=0, second=0)
    end_time = start_time + timedelta(hours=1)

    event = {
        "summary": f"Free Trial – {name}",
        "description": f"Phone: {phone}\nDemo Gym Free Trial",
        "start": {
            "dateTime": start_time.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
        "end": {
            "dateTime": end_time.isoformat(),
            "timeZone": "Asia/Kolkata",
        },
    }

    service.events().insert(
        calendarId=CALENDAR_ID,
        body=event
    ).execute()
