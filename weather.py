import datetime as dt
import requests
from config import OPENWEATHER_API_KEY

BASE_URL = "https://api.openweathermap.org/data/2.5/weather?"
API_KEY = OPENWEATHER_API_KEY
DEFAULT_CITY = "Spring"

def get_weather(city=DEFAULT_CITY):
    try:
        url = BASE_URL + "appid=" + API_KEY + "&q=" + city + "&units=imperial"
        response = requests.get(url).json()
        if response.get("cod") != 200:
            return None
        temp_fahrenheit = response["main"]["temp"]
        feels_like_fahrenheit = response["main"]['feels_like']
        wind_speed = response['wind']['speed']
        humidity = response["main"]['humidity']
        description = response['weather'][0]['description']
        sunrise_time = dt.datetime.utcfromtimestamp(response['sys']['sunrise'] + response['timezone'])
        sunset_time = dt.datetime.utcfromtimestamp(response['sys']['sunset'] + response['timezone'])
        return {
        "city": city,
        "description": description,
        "temp": round(temp_fahrenheit),
        "feels_like": round(feels_like_fahrenheit),
        "humidity": humidity,
        "wind_speed": round(wind_speed),
        "sunrise": sunrise_time,
        "sunset": sunset_time
        }
    except:
        return None