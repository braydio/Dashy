import os, json, requests
from datetime import datetime, timedelta
from flask import Flask, render_template, request
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY") or "YOUR_OPENWEATHERMAP_API_KEY"
LAT, LON = 35.7796, -78.6382
DATA_DIR = "./weather_data"
os.makedirs(DATA_DIR, exist_ok=True)


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
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={LAT}&lon={LON}&units=imperial&appid={API_KEY}"
    r = requests.get(url, timeout=10).json()
    sunrise = datetime.fromtimestamp(r["sys"]["sunrise"]).isoformat()
    sunset = datetime.fromtimestamp(r["sys"]["sunset"]).isoformat()
    now_data = {
        "sunrise": sunrise,
        "sunset": sunset,
        "retrieved_at": datetime.now().isoformat(),
    }
    today = datetime.now().date().isoformat()
    with open(cache_path(today, kind="now"), "w") as f:
        json.dump(now_data, f)


def load_forecast(days=5):
    today = datetime.now().date().isoformat()
    today_forecast_path = cache_path(today)
    today_now_path = cache_path(today, kind="now")

    if not is_cache_fresh(today_forecast_path):
        fetch_and_save_forecast()
    if not is_cache_fresh(today_now_path):
        fetch_and_cache_current_weather()

    with open(today_now_path) as f:
        sun = json.load(f)
    sunrise_dt = datetime.fromisoformat(sun["sunrise"])
    sunset_dt = datetime.fromisoformat(sun["sunset"])

    forecast = []
    for offset in range(days):
        date = (datetime.now().date() + timedelta(days=offset)).isoformat()
        path = cache_path(date)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)

            if offset == 0:
                data["sunrise"] = sun["sunrise"]
                data["sunset"] = sun["sunset"]
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
