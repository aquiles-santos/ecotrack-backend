from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.air_quality import AirQualityResponse
from app.services.openweather_service import OpenWeatherService

router = APIRouter(prefix="/air-quality", tags=["air-quality"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_openweather_service(session: SessionDep) -> OpenWeatherService:
    return OpenWeatherService(session)


OpenWeatherServiceDep = Annotated[
    OpenWeatherService,
    Depends(get_openweather_service),
]


@router.get("", response_model=AirQualityResponse)
async def get_air_quality(
    service: OpenWeatherServiceDep,
    lat: Annotated[float, Query(ge=-90, le=90)],
    lon: Annotated[float, Query(ge=-180, le=180)],
) -> AirQualityResponse:
    return await service.get_air_quality(lat=lat, lon=lon)
