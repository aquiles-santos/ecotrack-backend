from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.air_quality import Pollutants


class TargetPollutant(StrEnum):
    PM2_5 = "PM2.5"
    PM10 = "PM10"
    CO = "CO"
    NO2 = "NO2"
    O3 = "O3"


class Criticality(StrEnum):
    WITHIN_LIMIT = "within_limit"
    ABOVE_LIMIT = "above_limit"


POLLUTANT_FIELD_MAP: dict[TargetPollutant, str] = {
    TargetPollutant.PM2_5: "pm2_5",
    TargetPollutant.PM10: "pm10",
    TargetPollutant.CO: "co",
    TargetPollutant.NO2: "no2",
    TargetPollutant.O3: "o3",
}


class AlertCreate(BaseModel):
    local_name: str = Field(..., min_length=1, max_length=255)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    target_pollutant: TargetPollutant
    concentration_limit: float = Field(..., gt=0)


class AlertUpdate(BaseModel):
    local_name: str | None = Field(default=None, min_length=1, max_length=255)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    target_pollutant: TargetPollutant | None = None
    concentration_limit: float | None = Field(default=None, gt=0)


class LatestReading(BaseModel):
    pollutants: Pollutants
    aqi: int = Field(..., ge=1, le=5)
    fetched_at: datetime


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    local_name: str
    latitude: float
    longitude: float
    target_pollutant: TargetPollutant
    concentration_limit: float
    created_at: datetime
    updated_at: datetime
    latest_reading: LatestReading | None = None
    criticality: Criticality | None = None
