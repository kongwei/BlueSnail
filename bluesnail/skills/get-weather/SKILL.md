---
name: get-weather
description: Query current weather information for a city. Use when the user asks about weather, temperature, forecasts, or whether they need an umbrella.
---

# Get Weather

## Instructions

1. Extract the target city from the user request.
2. Run the bundled script with `run_skill_script`:

```json
{
  "skill": "get-weather",
  "script": "scripts/get_weather.py",
  "arguments": ["--city", "<CITY>"]
}
```

Equivalent shell form (from this skill directory):

```bash
python scripts/get_weather.py --city "<CITY>"
```

3. Summarize the returned JSON weather data in concise natural language.

## Available scripts

- **`scripts/get_weather.py`** — Fetches live weather from Open-Meteo (no API key).

## Output

The script prints structured JSON containing:

- `city`
- `country`
- `weather`
- `weather_code`
- `temperature`
- `humidity`
- `wind_speed`
- `source` (open-meteo.com)

## Examples

User: 上海今天天气怎么样？
Action: `run_skill_script` with skill=`get-weather`, script=`scripts/get_weather.py`, arguments=`["--city", "上海"]`

User: What's the weather in Beijing?
Action: `run_skill_script` with skill=`get-weather`, script=`scripts/get_weather.py`, arguments=`["--city", "Beijing"]`
