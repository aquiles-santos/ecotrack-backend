from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.air_quality import PollutantGlossary
from app.services.pollutant_service import PollutantService

router = APIRouter(prefix="/pollutants", tags=["pollutants"])


def get_pollutant_service() -> PollutantService:
    return PollutantService()


PollutantServiceDep = Annotated[PollutantService, Depends(get_pollutant_service)]


@router.get(
    "",
    response_model=PollutantGlossary,
    summary="Significado de cada poluente",
    description=(
        "Dicionário estático. As chaves são as mesmas de `pollutants` em "
        "GET /air-quality: pm2_5, pm10, co, no2 e o3. Cada valor traz `name` "
        "e `description` (o que é, efeito na saúde e referência OMS)."
    ),
)
async def list_pollutant_meanings(
    service: PollutantServiceDep,
) -> PollutantGlossary:
    return service.glossary()
