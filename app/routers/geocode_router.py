from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.schemas.geocode import GeocodeResponse
from app.services.geocode_service import GeocodeService

router = APIRouter(prefix="/geocode", tags=["geocode"])


def get_geocode_service() -> GeocodeService:
    return GeocodeService()


GeocodeServiceDep = Annotated[GeocodeService, Depends(get_geocode_service)]


@router.get("", response_model=GeocodeResponse)
async def geocode(
    service: GeocodeServiceDep,
    q: Annotated[str, Query(min_length=1, max_length=255)],
    limit: Annotated[int, Query(ge=1, le=5)] = 5,
) -> GeocodeResponse:
    return await service.geocode(query=q, limit=limit)
