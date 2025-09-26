"""Flask application utilities for the Weatherboy dashboard.

This module handles fetching, caching, and presenting weather data from
OpenWeatherMap so that the dashboard can render forecasts quickly without
relying on live API calls for every request.
"""

import json
import os
from datetime import datetime, timedelta

import requests
from dotenv import load_dotenv
from flask import Flask, render_template, request

load_dotenv()

API_KEY = os.getenv("API_KEY") or "YOUR_OPENWEATHERMAP_API_KEY"
LAT, LON = 35.7796, -78.6382
DATA_DIR = "./weather_data"
os.makedirs(DATA_DIR, exist_ok=True)


def _iso_from_timestamp(timestamp):
    """Convert a Unix timestamp to an ISO 8601 string.

    Args:
        timestamp (int | float | None): The timestamp to convert.

    Returns:
        str | None: The ISO formatted timestamp if the input is valid, otherwise
        ``None``.
    """

    if timestamp is None:
        return None
    try:
        return datetime.fromtimestamp(timestamp).isoformat()
    except (OSError, OverflowError, TypeError, ValueError):
        return None


def get_icon(desc):
    desc = desc.lower()
    if "thunder" in desc:
        return "⛈️"
    if "snow" in desc:
        return "❄️"
    if "rain" in desc:
        return "🌧️"
    if "cloud" in desc:
        return "☁️"
    if "clear" in desc:
        return "☀️"
    return "🌤️"


def cache_path(date, kind="forecast"):
    suffix = "_now.json" if kind == "now" else ".json"
    return os.path.join(DATA_DIR, f"{date}{suffix}")


def is_cache_fresh(path, max_age_hours=1):
    if not os.path.exists(path):
        return False
    mtime = os.path.getmtime(path)
    age = (datetime.now() - datetime.fromtimestamp(mtime)).total_seconds() / 3600
    return age < max_age_hours


def fetch_and_save_forecast():
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={LAT}&lon={LON}&units=imperial&appid={API_KEY}"
    data = requests.get(url, timeout=10).json()
    days = {}
    for entry in data.get("list", []):
        date = entry["dt_txt"].split()[0]
        main, weather = entry["main"], entry["weather"][0]
        day = days.setdefault(
            date,
            {
                "temps": [],
                "weather": [],
                "raw_entries": [],
                "date": date,
            },
        )
        day["temps"].append(main["temp"])
        day["weather"].append(weather["description"])
        day["raw_entries"].append(entry)
    for date, vals in days.items():
        desc = max(set(vals["weather"]), key=vals["weather"].count)
        summary = desc.capitalize()
        min_temp = round(min(vals["temps"]), 1)
        max_temp = round(max(vals["temps"]), 1)
        out = {
            "date": date,
            "weekday": datetime.strptime(date, "%Y-%m-%d").strftime("%a"),
            "temp_min": min_temp,
            "temp_max": max_temp,
            "icon": get_icon(desc),
            "summary": summary,
            "weather_descriptions": vals["weather"],
            "temps": vals["temps"],
            "raw_entries": vals["raw_entries"],
            "source": "openweathermap",
            "retrieved_at": datetime.now().isoformat(),
        }
        with open(cache_path(date), "w") as f:
            json.dump(out, f)


def fetch_and_cache_current_weather():
    """Fetch current sunrise and sunset data and cache it locally.

    The OpenWeatherMap API occasionally returns error payloads (for example,
    when the configured API key is invalid) that do not include the ``sys``
    field. This helper now guards against such scenarios by reusing previously
    cached data when available and by falling back to reasonable defaults when
    necessary.

    Returns:
        dict: The payload persisted to the cache for the current day.
    """

    url = (
        "https://api.openweathermap.org/data/2.5/weather?"
        f"lat={LAT}&lon={LON}&units=imperial&appid={API_KEY}"
    )
    payload = {}
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        payload = {}

    sys_info = payload.get("sys") or {}
    sunrise_iso = _iso_from_timestamp(sys_info.get("sunrise"))
    sunset_iso = _iso_from_timestamp(sys_info.get("sunset"))

    today = datetime.now().date().isoformat()
    cache_file = cache_path(today, kind="now")

    cached_payload = {}
    if os.path.exists(cache_file):
        with open(cache_file) as existing_cache:
            try:
                cached_payload = json.load(existing_cache)
            except json.JSONDecodeError:
                cached_payload = {}

    sunrise_iso = sunrise_iso or cached_payload.get("sunrise")
    sunset_iso = sunset_iso or cached_payload.get("sunset")

    if not sunrise_iso or not sunset_iso:
        now = datetime.now()
        default_sunrise = now.replace(hour=6, minute=0, second=0, microsecond=0)
        default_sunset = now.replace(hour=18, minute=0, second=0, microsecond=0)
        sunrise_iso = sunrise_iso or default_sunrise.isoformat()
        sunset_iso = sunset_iso or default_sunset.isoformat()

    now_data = {
        "sunrise": sunrise_iso,
        "sunset": sunset_iso,
        "retrieved_at": datetime.now().isoformat(),
        "source": payload.get("name") or "openweathermap",
    }

    with open(cache_file, "w") as cache_handle:
        json.dump(now_data, cache_handle)

    return now_data


def load_forecast(days=5):
    """Return a list of forecast dictionaries for the requested number of days."""

    today = datetime.now().date().isoformat()
    today_forecast_path = cache_path(today)
    today_now_path = cache_path(today, kind="now")

    if not is_cache_fresh(today_forecast_path):
        fetch_and_save_forecast()
    if not is_cache_fresh(today_now_path):
        fetch_and_cache_current_weather()

    with open(today_now_path) as f:
        sun = json.load(f)

    sunrise_raw = sun.get("sunrise")
    sunset_raw = sun.get("sunset")

    sunrise_dt = None
    sunset_dt = None
    if sunrise_raw:
        try:
            sunrise_dt = datetime.fromisoformat(sunrise_raw)
        except ValueError:
            sunrise_dt = None
    if sunset_raw:
        try:
            sunset_dt = datetime.fromisoformat(sunset_raw)
        except ValueError:
            sunset_dt = None

    forecast = []
    for offset in range(days):
        date = (datetime.now().date() + timedelta(days=offset)).isoformat()
        path = cache_path(date)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)

            if offset == 0:
                data["sunrise"] = sunrise_raw
                data["sunset"] = sunset_raw
                if sunrise_dt and sunset_dt:
                    data["daylight_bounds"] = {
                        "sunrise_hour": sunrise_dt.hour,
                        "sunset_hour": sunset_dt.hour,
                    }

            forecast.append(
                {
                    "date": data["date"],
                    "weekday": data["weekday"],
                    "temp_min": data["temp_min"],
                    "temp_max": data["temp_max"],
                    "icon": data["icon"],
                    "summary": data["summary"],
                    "raw_entries": data.get("raw_entries", []),
                    "sunrise": data.get("sunrise"),
                    "sunset": data.get("sunset"),
                    "daylight_bounds": data.get("daylight_bounds"),
                }
            )
    return forecast


app = Flask(__name__)


@app.after_request
def add_header(response):
    response.headers["X-Frame-Options"] = "ALLOWALL"
    return response


@app.template_filter("datetimeformat")
def datetimeformat(value, format="%I%p"):
    try:
        return (
            datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
            .strftime(format)
            .lstrip("0")
            .lower()
        )
    except Exception:
        return value


@app.route("/")
def index():
    tmpl = request.args.get("tmpl", "main")
    selected_day = int(request.args.get("day", 0))

    forecast = load_forecast()
    if selected_day < 0 or selected_day >= len(forecast):
        selected_day = 0

    return render_template(
        f"{tmpl}.html", forecast=forecast, now=datetime.now(), selected_day=selected_day
    )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5170)
