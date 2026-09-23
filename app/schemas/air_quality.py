from datetime import datetime
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, Field, model_validator


class AirQualitySource(StrEnum):
    CACHE = "cache"
    OPENWEATHER = "openweather"
    UNAVAILABLE_FALLBACK = "unavailable_fallback"


class Pollutants(BaseModel):
    pm2_5: float | None = None
    pm10: float | None = None
    co: float | None = None
    no2: float | None = None
    o3: float | None = None


class AirQualityQuery(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)


class AirQualityResponse(BaseModel):
    lat: float
    lon: float
    pollutants: Pollutants
    aqi: int | None = Field(default=None, ge=1, le=5)
    source: AirQualitySource
    fetched_at: datetime
    stale: bool = False

    @model_validator(mode="after")
    def aqi_matches_source(self) -> Self:
        if self.source is AirQualitySource.UNAVAILABLE_FALLBACK:
            if self.aqi is not None:
                raise ValueError("aqi must be absent for unavailable_fallback")
            return self
        if self.aqi is None:
            raise ValueError("aqi is required when air quality data is available")
        return self
