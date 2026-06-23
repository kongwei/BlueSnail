"""Handler for the get-weather skill."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
USER_AGENT = "BlueSnail/0.1 (weather skill)"

_WMO_DESCRIPTIONS = {
    0: "clear sky",
    1: "mainly clear",
    2: "partly cloudy",
    3: "overcast",
    45: "fog",
    48: "depositing rime fog",
    51: "light drizzle",
    53: "moderate drizzle",
    55: "dense drizzle",
    61: "slight rain",
    63: "moderate rain",
    65: "heavy rain",
    71: "slight snow",
    73: "moderate snow",
    75: "heavy snow",
    80: "rain showers",
    81: "moderate rain showers",
    82: "violent rain showers",
    95: "thunderstorm",
    96: "thunderstorm with slight hail",
    99: "thunderstorm with heavy hail",
}


def run(city: str) -> dict[str, str | float]:
    """Return current weather for the requested city."""
    city = city.strip()
    if not city:
        raise ValueError("city is required")
    return fetch_weather(city)


def fetch_weather(city: str) -> dict[str, str | float]:
    location = geocode_city(city)
    forecast = fetch_forecast(location["latitude"], location["longitude"])
    current = forecast["current"]

    temperature = current["temperature_2m"]
    weather_code = int(current.get("weather_code", 0))
    resolved_name = location.get("name") or city
    country = location.get("country") or ""

    return {
        "city": resolved_name,
        "country": country,
        "weather": describe_weather_code(weather_code),
        "weather_code": weather_code,
        "temperature": f"{temperature}C",
        "humidity": f"{current.get('relative_humidity_2m', '')}%",
        "wind_speed": f"{current.get('wind_speed_10m', '')} km/h",
        "source": "open-meteo.com",
    }


def geocode_city(city: str) -> dict:
    data = http_get_json(
        GEOCODING_URL,
        {
            "name": city,
            "count": 1,
            "language": "zh",
        },
    )
    results = data.get("results") or []
    if not results:
        raise ValueError(f"City not found: {city}")
    return results[0]


def fetch_forecast(latitude: float, longitude: float) -> dict:
    return http_get_json(
        FORECAST_URL,
        {
            "latitude": latitude,
            "longitude": longitude,
            "current": "temperature_2m,relative_humidity_2m,weather_code,wind_speed_10m",
            "timezone": "auto",
        },
    )


def describe_weather_code(code: int) -> str:
    if code in _WMO_DESCRIPTIONS:
        return _WMO_DESCRIPTIONS[code]
    if code in range(56, 58):
        return "freezing drizzle"
    if code in range(66, 68):
        return "freezing rain"
    if code in range(85, 87):
        return "snow showers"
    return "unknown"


def http_get_json(base_url: str, params: dict) -> dict:
    query = urllib.parse.urlencode(params)
    url = f"{base_url}?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Weather API HTTP error: {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Weather API connection failed: {exc.reason}") from exc

    data = json.loads(payload)
    if not isinstance(data, dict):
        raise RuntimeError("Weather API returned invalid JSON payload")
    return data
