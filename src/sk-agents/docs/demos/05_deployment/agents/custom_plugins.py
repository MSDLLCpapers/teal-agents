from enum import Enum

from pydantic import BaseModel
from semantic_kernel.functions.kernel_function_decorator import kernel_function

from sk_agents.ska_types import BasePlugin


class Location(Enum):
    RAHWAY = "Rahway"
    WEST_POINT = "West Point"
    AUSTIN = "Austin"
    BENTONVILLE = "Bentonville"


class LocationCoordinates(BaseModel):
    location: Location
    latitude: float
    longitude: float
    timezone: str


class CoordinatesPlugin(BasePlugin):
    locations: dict[Location, LocationCoordinates] = {
        Location.RAHWAY: LocationCoordinates(
            location=Location.RAHWAY,
            latitude=40.6082,
            longitude=-74.2777,
            timezone="America/New_York",
        ),
        Location.WEST_POINT: LocationCoordinates(
            location=Location.WEST_POINT,
            latitude=41.3911,
            longitude=-73.9559,
            timezone="America/New_York",
        ),
        Location.AUSTIN: LocationCoordinates(
            location=Location.AUSTIN,
            latitude=30.2672,
            longitude=-97.7431,
            timezone="America/Chicago",
        ),
        Location.BENTONVILLE: LocationCoordinates(
            location=Location.AUSTIN,
            latitude=36.3724,
            longitude=-94.2102,
            timezone="America/Chicago",
        ),
    }

    @kernel_function(description="Retrieve coordinates for a given location")
    def get_coordinates(self, location: Location) -> LocationCoordinates:
        if location not in self.locations:
            raise ValueError(f"Location {location} not found")
        return self.locations[location]
