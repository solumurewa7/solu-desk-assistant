import os
import sys
import threading
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# ------------------------------------------------------------------

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_FILE = os.path.join(BASE_DIR, "credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
SOLU_CALENDAR_ID = "7048791d55b63aaaa359ede2ed94e9db45cd28b4d780566d53c7769181ea75af@group.calendar.google.com"
TIMEZONE = "America/Chicago"

_service = None
_creds = None
_lock = threading.RLock()  # the API client isn't thread-safe, so calls go through this too

# ------------------------------------------------------------------

def authenticate():
    """Returns a Calendar API client, refreshing the saved token as needed.
    The browser sign-in only runs from a terminal (do it on the laptop and
    copy token.json over); on the Pi it raises instead of hanging forever."""
    global _service, _creds
    with _lock:
        if _service is not None and _creds.valid:
            return _service

        creds = None
        if os.path.exists(TOKEN_FILE):
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif sys.stdin is not None and sys.stdin.isatty():
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                creds = flow.run_local_server(port=0)
            else:
                raise RuntimeError("calendar: token.json missing or revoked, re-run sign-in on the laptop and copy it over")
            with open(TOKEN_FILE, "w") as token:
                token.write(creds.to_json())

        _creds = creds
        _service = build("calendar", "v3", credentials=creds, cache_discovery=False)
        return _service

# ------------------------------------------------------------------

def add_event(message, date, time_str, duration_hours=1):
    """Adds an event to Solu's calendar. Returns True on success."""
    try:
        start = datetime.fromisoformat(f"{date}T{time_str}:00")
        end = start + timedelta(hours=duration_hours)
        event = {
            "summary": message,
            "start": {"dateTime": start.isoformat(), "timeZone": TIMEZONE},
            "end": {"dateTime": end.isoformat(), "timeZone": TIMEZONE},
        }
        with _lock:
            authenticate().events().insert(calendarId=SOLU_CALENDAR_ID, body=event).execute()
        return True
    except Exception as e:
        print(f"calendar: couldn't add event {message!r}: {e!r}")
        return False

# ------------------------------------------------------------------
# reading events (not wired up to Solu yet)
# ------------------------------------------------------------------

def get_events(start_day, days, calendar_id="primary"):
    """Events from local midnight on start_day through the next `days` days."""
    tz = ZoneInfo(TIMEZONE)
    start = datetime.combine(start_day, time.min, tz)
    end = start + timedelta(days=days)
    with _lock:
        result = authenticate().events().list(
            calendarId=calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        ).execute()
    return result.get("items", [])


def _today():
    return datetime.now(ZoneInfo(TIMEZONE)).date()


def get_events_today(calendar_id="primary"):
    return get_events(_today(), 1, calendar_id)


def get_events_tomorrow(calendar_id="primary"):
    return get_events(_today() + timedelta(days=1), 1, calendar_id)


def get_events_this_week(calendar_id="primary"):
    return get_events(_today(), 7, calendar_id)


def get_events_this_month(calendar_id="primary"):
    first = _today().replace(day=1)
    next_month = (first + timedelta(days=32)).replace(day=1)
    return get_events(first, (next_month - first).days, calendar_id)
