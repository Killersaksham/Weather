from flask import Flask, render_template, request
import requests
import logging
from flask_caching import Cache
from datetime import datetime
import pytz

app = Flask(__name__)

# --- Setup caching (5 min default) ---
cache = Cache(app, config={'CACHE_TYPE': 'SimpleCache', 'CACHE_DEFAULT_TIMEOUT': 300})

# --- Logging setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Geocoding API (Open-Meteo) ---
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"

# --- Weather API (Open-Meteo) ---
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# --- Weather Codes Mapping ---
WEATHER_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Fog", 48: "Depositing rime fog", 51: "Light drizzle", 53: "Moderate drizzle",
    55: "Dense drizzle", 61: "Rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Snow", 73: "Moderate snow", 75: "Heavy snow", 80: "Showers",
    81: "Heavy showers", 95: "Thunderstorm", 99: "Severe thunderstorm"
}


def c_to_f(c_temp):
    """Converts Celsius to Fahrenheit."""
    return (c_temp * 9 / 5) + 32


def format_date_helper(date_str):
    """Jinja2 filter to format date string."""
    return datetime.strptime(date_str, '%Y-%m-%d').strftime('%a, %b %d')


def slice_time_helper(time_str):
    """Jinja2 filter to extract time from datetime string."""
    return time_str.split('T')[1]


@app.context_processor
def utility_processor():
    """Adds a function to the Jinja2 context."""
    return dict(
        format_date=format_date_helper,
        slice_time=slice_time_helper,
        c_to_f=c_to_f,
        weather_codes=WEATHER_CODES
    )


def geocode_city(city_name):
    """Fetch latitude and longitude for a given city."""
    try:
        response = requests.get(GEOCODE_URL, params={
            "name": city_name,
            "count": 1,
            "language": "en",
            "format": "json"
        })
        response.raise_for_status()
        data = response.json()
        if "results" not in data:
            return None
        result = data["results"][0]
        return {
            "latitude": result["latitude"],
            "longitude": result["longitude"],
            "location_name": f"{result['name']}, {result.get('admin1', result['country'])}"
        }
    except Exception as e:
        logger.error(f"Geocoding error for {city_name}: {e}")
        return None


@cache.memoize()
def get_weather_data(lat, lon, units):
    """Fetch weather data from Open-Meteo with specific units."""
    try:
        params = {
            "latitude": lat,
            "longitude": lon,
            "current_weather": True,
            "hourly": "temperature_2m,apparent_temperature,weathercode,precipitation_probability",
            "daily": "weathercode,temperature_2m_max,temperature_2m_min,sunrise,sunset,precipitation_probability_max,relative_humidity_2m_max",
            "timezone": "auto",
            "temperature_unit": units
        }
        response = requests.get(WEATHER_URL, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Weather API error: {e}")
        return None


@app.route("/", methods=["GET"])
def index():
    location_query = request.args.get("location")
    units = request.args.get("units", "metric")  # Default to Celsius

    weather_data = None
    error = None

    if location_query:
        geo = geocode_city(location_query)
        if geo:
            weather_data = get_weather_data(geo["latitude"], geo["longitude"], units)
            if weather_data:
                weather_data["locationName"] = geo["location_name"]
            else:
                error = f"Could not fetch weather for '{geo['location_name']}'."
        else:
            error = f"Could not find '{location_query}'. Try another city."

    # Handle the time and timezone for display
    now = datetime.now()
    if weather_data and 'timezone' in weather_data:
        local_timezone = pytz.timezone(weather_data['timezone'])
        now = datetime.now(local_timezone)

    return render_template(
        "index.html",
        weather_data=weather_data,
        error=error,
        location_query=location_query,
        units=units,
        now=now,
        current=weather_data['current_weather'] if weather_data else None,
        daily=weather_data['daily'] if weather_data else None
    )


if __name__ == "__main__":
    app.run(debug=True)