from datetime import datetime, timedelta, timezone

import requests

from config import OPENWEATHER_API_KEY

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"
DEFAULT_CITY = "College Station"
REQUEST_TIMEOUT = 5  # seconds, so a bad connection can't hang the caller

_session = requests.Session()  # reuses the connection between refreshes


def get_weather(city=DEFAULT_CITY):
    """Current weather as a dict, or None if it can't be fetched."""
    try:
        response = _session.get(
            BASE_URL,
            params={"appid": OPENWEATHER_API_KEY, "q": city, "units": "imperial"},
            timeout=REQUEST_TIMEOUT,
        )
        data = response.json()
        if str(data.get("cod")) != "200":
            print(f"weather: API error: {data.get('message', data.get('cod'))}")
            return None

        local_tz = timezone(timedelta(seconds=data["timezone"]))
        return {
            "city": city,
            "description": data["weather"][0]["description"],
            "temp": round(data["main"]["temp"]),
            "feels_like": round(data["main"]["feels_like"]),
            "humidity": data["main"]["humidity"],
            "wind_speed": round(data["wind"]["speed"]),
            "sunrise": datetime.fromtimestamp(data["sys"]["sunrise"], local_tz),
            "sunset": datetime.fromtimestamp(data["sys"]["sunset"], local_tz),
        }
    except (requests.RequestException, ValueError, KeyError, IndexError, TypeError) as e:
        print(f"weather: fetch failed: {e!r}")
        return None
