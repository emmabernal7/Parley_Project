"""Open-Meteo weather (free, no API key).  Used for outdoor sports at kickoff time and place."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, Optional

import requests

log = logging.getLogger(__name__)
GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST = "https://api.open-meteo.com/v1/forecast"
TIMEOUT = 6

WMO_CODE = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog",
            51: "Light drizzle", 53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain",
            65: "Heavy rain", 71: "Light snow", 73: "Snow", 75: "Heavy snow", 80: "Rain showers",
            81: "Rain showers", 82: "Violent showers", 95: "Thunderstorm", 96: "Thunderstorm (hail)"}


def geocode(city: str, country: Optional[str] = None) -> Optional[Dict]:
    try:
        r = requests.get(GEOCODE, params={"name": city, "count": 5}, timeout=TIMEOUT)
        r.raise_for_status()
        results = r.json().get("results") or []
    except requests.RequestException as e:
        log.info("geocoding failed for %s: %s", city, e)
        return None
    if country:
        for res in results:
            if str(res.get("country", "")).lower().startswith(country.lower()[:3]):
                return res
    return results[0] if results else None


def forecast_at(lat: float, lon: float, when: datetime) -> Optional[Dict]:
    try:
        r = requests.get(FORECAST, params={
            "latitude": lat, "longitude": lon, "timezone": "UTC",
            "hourly": "temperature_2m,precipitation,wind_speed_10m,wind_gusts_10m,weather_code",
        }, timeout=TIMEOUT)
        r.raise_for_status()
        h = r.json().get("hourly", {})
    except requests.RequestException as e:
        log.info("forecast failed for (%s,%s): %s", lat, lon, e)
        return None
    times = h.get("time", [])
    target = when.strftime("%Y-%m-%dT%H:00")
    if target not in times:
        return None
    i = times.index(target)
    code = int(h["weather_code"][i])
    return {"temp_c": h["temperature_2m"][i], "precip_mm": h["precipitation"][i], "wind_kmh": h["wind_speed_10m"][i],
            "gust_kmh": h["wind_gusts_10m"][i], "code": code, "condition": WMO_CODE.get(code, "Unknown")}


def weather_for_event(city: Optional[str], country: Optional[str], when: datetime) -> Optional[Dict]:
    if not city:
        return None
    loc = geocode(city, country)
    if not loc:
        return None
    return forecast_at(loc["latitude"], loc["longitude"], when)


def goal_rate_multiplier(weather: Optional[Dict]) -> float:
    """Rough, UNCALIBRATED prior: heavy rain/wind slightly favours fewer goals. Off by default
    (see Settings.weather_adjust) until it can be fitted against real goal counts."""
    if not weather:
        return 1.0
    mult = 1.0
    if weather.get("wind_kmh", 0) > 35:
        mult *= 0.95
    if weather.get("precip_mm", 0) > 2.0:
        mult *= 0.97
    if weather.get("code", 0) >= 95:
        mult *= 0.93
    return mult
