from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone
import calendar
import os

#-------------------------------------------------------------------------------------------------------------------------------------------

SCOPES = ['https://www.googleapis.com/auth/calendar']
CREDENTIALS_FILE = "credentials.json"
TOKEN_FILE = "token.json"
SOLU_CALENDAR_ID = "7048791d55b63aaaa359ede2ed94e9db45cd28b4d780566d53c7769181ea75af@group.calendar.google.com"

#-------------------------------------------------------------------------------------------------------------------------------------------

def authenticate():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)

#-------------------------------------------------------------------------------------------------------------------------------------------

def add_event(message, date, time, duration_hours=1):
    try:
        start_time = f"{date}T{time}:00"
        datetime_start_time = datetime.fromisoformat(start_time)
        datetime_end_time = datetime_start_time + timedelta(hours=duration_hours)
        end_time = datetime_end_time.isoformat()
        event = {
        "summary": message,
        "start": {
            "dateTime": start_time,
            "timeZone": "America/Chicago"
        },
        "end": {
            "dateTime": end_time,
            "timeZone": "America/Chicago"
        }
                }
        service = authenticate()
        service.events().insert(calendarId=SOLU_CALENDAR_ID, body=event).execute()
        return True
    except:
        return False

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_events_today():
    service = authenticate()
    now = datetime.now(timezone.utc)
    datetime_today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    datetime_today_end = datetime_today_start + timedelta(days=1)
    today_start = datetime_today_start.isoformat()
    today_end = datetime_today_end.isoformat()

    dict_todays_events = service.events().list(
    calendarId='primary',
    timeMin=today_start,
    timeMax=today_end,
    singleEvents=True,  
    orderBy='startTime' 
    ).execute()

    todays_events = dict_todays_events.get('items', [])
    return todays_events

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_events_tomorrow():
    service = authenticate()
    now = datetime.now(timezone.utc)
    datetime_tomorrow_start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    datetime_tomorrow_end = datetime_tomorrow_start + timedelta(days=1)
    tomorrow_start = datetime_tomorrow_start.isoformat()
    tomorrow_end = datetime_tomorrow_end.isoformat()

    dict_tomorrows_events = service.events().list(
    calendarId='primary',
    timeMin=tomorrow_start,
    timeMax=tomorrow_end,
    singleEvents=True,  
    orderBy='startTime' 
    ).execute()

    tomorrows_events = dict_tomorrows_events.get('items', [])
    return tomorrows_events

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_events_this_week():
    service = authenticate()
    now = datetime.now(timezone.utc)
    datetime_week_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    datetime_week_end = datetime_week_start + timedelta(days=7)
    week_start = datetime_week_start.isoformat()
    week_end = datetime_week_end.isoformat()

    dict_weeks_events = service.events().list(
    calendarId='primary',
    timeMin=week_start,
    timeMax=week_end,
    singleEvents=True,  
    orderBy='startTime' 
    ).execute()

    this_weeks_events = dict_weeks_events.get('items', [])
    return this_weeks_events

#-------------------------------------------------------------------------------------------------------------------------------------------

def get_events_this_month():
    service = authenticate()
    now = datetime.now(timezone.utc)
    datetime_month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0); last_day = calendar.monthrange(now.year, now.month)[1]
    datetime_month_end = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=0)
    month_start = datetime_month_start.isoformat()
    month_end = datetime_month_end.isoformat()

    dict_months_events = service.events().list(
    calendarId='primary',
    timeMin=month_start,
    timeMax=month_end,
    singleEvents=True,  
    orderBy='startTime' 
    ).execute()

    this_months_events = dict_months_events.get('items', [])
    return this_months_events
