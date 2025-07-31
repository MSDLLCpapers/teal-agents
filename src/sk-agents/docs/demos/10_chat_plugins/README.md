# Chat-Only Agents with PlugIns
Chat-only agents do support the same plug-in architecture as sequential agents.

### Example Configuration

```yaml
apiVersion: skagents/v1
kind: Chat
description: >
  A weather chat agent
service_name: WeatherBot
version: 0.1
input_type: BaseInputWithUserContext
spec:
  agent:
    name: default
    role: Default Agent
    model: gpt-4o
    system_prompt: >
      You are a helpful assistant.
    plugins:
    - WeatherPlugin
```

### Example Custom Plugin

```python
import requests
from pydantic import BaseModel, ConfigDict
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from sk_agents.ska_types import BasePlugin


class LocationCoordinates(BaseModel):
    latitude: float
    longitude: float
    timezone: str


class DailyUnits(BaseModel):
    time: str
    temperature_2m_max: str
    temperature_2m_min: str


class Daily(BaseModel):
    time: list[str]
    temperature_2m_max: list[float]
    temperature_2m_min: list[float]


class TemperatureResponseInt(BaseModel):
    latitude: float
    longitude: float
    generationtime_ms: float
    utc_offset_seconds: int
    timezone: str
    timezone_abbreviation: str
    elevation: int
    daily_units: DailyUnits
    daily: Daily


class TemperatureResponse(BaseModel):
    low: float
    high: float


class TimeZone(BaseModel):
    model_config = ConfigDict(extra="allow")
    timeZoneId: str


class GeoName(BaseModel):
    model_config = ConfigDict(extra="allow")
    timezone: TimeZone
    lat: float
    lng: float


class CoordsResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    geonames: list[GeoName]


class WeatherPlugin(BasePlugin):
    @staticmethod
    def _get_temp_url_for_location(lat: float, lng: float, timezone: str) -> str:
        return f"https://api.open-meteo.com/v1/forecast?latitude={str(lat)}&longitude={str(lng)}&daily=temperature_2m_max,temperature_2m_min&temperature_unit=fahrenheit&wind_speed_unit=mph&precipitation_unit=inch&timezone={timezone}&forecast_days=1"

    @staticmethod
    def _get_loc_url_for_location(self, location_string: str) -> str:
        return f"http://api.geonames.org/searchJSON?formatted=true&q={location_string}&maxRows=1&lang=en&username=tealagents&style=full"

    @kernel_function(
        description="Retrieve low and high temperatures for the day for a given location"
    )
    def get_temperature(self, lat: float, lng: float, timezone: str) -> TemperatureResponse:
        url = WeatherPlugin._get_temp_url_for_location(lat, lng, timezone)

        response = requests.get(url).json()
        if response:
            response_int: TemperatureResponseInt = TemperatureResponseInt(**response)
            return TemperatureResponse(
                low=response_int.daily.temperature_2m_min[0],
                high=response_int.daily.temperature_2m_max[0],
            )
        else:
            raise ValueError("Error retrieving temperature")

    @kernel_function(
        description="Retrieve the latitude, longitude, and timezone \
            for a given location search string"
    )
    def get_lat_lng_for_location(self, location_string: str) -> LocationCoordinates:
        url = WeatherPlugin._get_loc_url_for_location(self, location_string)

        response = requests.get(url).json()
        if response:
            response_int: CoordsResponse = CoordsResponse(**response)
            return LocationCoordinates(
                latitude=response_int.geonames[0].lat,
                longitude=response_int.geonames[0].lng,
                timezone=response_int.geonames[0].timezone.timeZoneId,
            )
        else:
            raise ValueError("Error retrieving location coordinates")
```
