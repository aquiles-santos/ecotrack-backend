from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


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
    aqi: int = Field(..., ge=1, le=5)
    source: AirQualitySource
    fetched_at: datetime
    stale: bool = False
