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


def cache_path(date):
    return os.path.join(DATA_DIR, f"{date}.json")


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


def load_forecast(days=5):
    today = datetime.now().date().isoformat()
    today_cache = cache_path(today)
    if not is_cache_fresh(today_cache):
        fetch_and_save_forecast()
    forecast = []
    for offset in range(days):
        date = (datetime.now().date() + timedelta(days=offset)).isoformat()
        path = cache_path(date)
        if os.path.exists(path):
            with open(path) as f:
                data = json.load(f)
            forecast.append(
                {
                    "date": data["date"],
                    "weekday": data["weekday"],
                    "temp_min": data["temp_min"],
                    "temp_max": data["temp_max"],
                    "icon": data["icon"],
                    "summary": data["summary"],
                    "raw_entries": data.get("raw_entries", []),
                }
            )
    return forecast


app = Flask(__name__)


@app.after_request
def add_header(response):
    response.headers["X-Frame-Options"] = "ALLOWALL"
    return response


@app.route("/")
def index():
    forecast = load_forecast()
    tmpl = request.args.get("tmpl", "main")
    # main.html, hourly_chart.html, etc.
    return render_template(f"{tmpl}.html", forecast=forecast)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5170)
