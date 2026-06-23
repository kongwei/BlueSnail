---
name: get-weather
description: Query current weather information for a city. Use when the user asks about weather, temperature, forecasts, or whether they need an umbrella.
disable-model-invocation: false
---

# Get Weather

## Instructions

1. Extract the target city from the user request.
2. Invoke this skill with the `city` argument.
3. Summarize the returned weather data in concise natural language.

## Output

Return structured JSON containing:

- `city`
- `country`
- `weather`
- `weather_code`
- `temperature`
- `humidity`
- `wind_speed`
- `source` (open-meteo.com)

Data is fetched live from the Open-Meteo geocoding and forecast APIs. No API key is required.

## Examples

User: 上海今天天气怎么样？
Action: call `get-weather` with `{ "city": "上海" }`

User: What's the weather in Beijing?
Action: call `get-weather` with `{ "city": "Beijing" }`
