import uuid
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import alert as alert_repo
from app.schemas.air_quality import Pollutants
from app.schemas.alert import (
    POLLUTANT_FIELD_MAP,
    AlertCreate,
    AlertRead,
    AlertUpdate,
    Criticality,
    LatestReading,
    TargetPollutant,
)


def _parse_pollutants(payload: dict) -> Pollutants:
    raw = payload.get("pollutants") or payload.get("components") or {}
    return Pollutants(
        pm2_5=raw.get("pm2_5"),
        pm10=raw.get("pm10"),
        co=raw.get("co"),
        no2=raw.get("no2"),
        o3=raw.get("o3"),
    )


def cache_to_latest_reading(cache: alert_repo.ReadingCache) -> LatestReading:
    return LatestReading(
        pollutants=_parse_pollutants(cache.payload_json),
        aqi=cache.aqi,
        fetched_at=cache.fetched_at,
    )


def compute_criticality(
    target_pollutant: TargetPollutant,
    concentration_limit: float | Decimal,
    latest_reading: LatestReading | None,
) -> Criticality | None:
    if latest_reading is None:
        return None

    field_name = POLLUTANT_FIELD_MAP[target_pollutant]
    concentration = getattr(latest_reading.pollutants, field_name)
    if concentration is None:
        return None

    limit = float(concentration_limit)
    if concentration <= limit:
        return Criticality.WITHIN_LIMIT
    return Criticality.ABOVE_LIMIT


async def build_alert_read(
    session: AsyncSession,
    alert: alert_repo.Alert,
    cache: alert_repo.ReadingCache | None = None,
    *,
    cache_loaded: bool = False,
) -> AlertRead:
    if not cache_loaded:
        cache = await alert_repo.get_cache(
            session,
            float(alert.latitude),
            float(alert.longitude),
        )
    latest_reading = cache_to_latest_reading(cache) if cache is not None else None
    criticality = compute_criticality(
        alert.target_pollutant,
        alert.concentration_limit,
        latest_reading,
    )
    return AlertRead(
        id=alert.id,
        local_name=alert.local_name,
        latitude=float(alert.latitude),
        longitude=float(alert.longitude),
        target_pollutant=alert.target_pollutant,
        concentration_limit=float(alert.concentration_limit),
        created_at=alert.created_at,
        updated_at=alert.updated_at,
        latest_reading=latest_reading,
        criticality=criticality,
    )


class AlertService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_alerts(
        self,
        skip: int = 0,
        limit: int = 50,
        criticality: Criticality | None = None,
    ) -> list[AlertRead]:
        rows = await alert_repo.list_alerts(
            self._session,
            skip=skip,
            limit=limit,
            criticality=criticality,
        )
        return [
            await build_alert_read(self._session, alert, cache, cache_loaded=True)
            for alert, cache in rows
        ]

    async def create_alert(self, data: AlertCreate) -> AlertRead:
        alert = await alert_repo.create_alert(self._session, data)
        return await build_alert_read(self._session, alert)

    async def update_alert(
        self,
        alert_id: uuid.UUID,
        data: AlertUpdate,
    ) -> AlertRead | None:
        alert = await alert_repo.update_alert(self._session, alert_id, data)
        if alert is None:
            return None
        return await build_alert_read(self._session, alert)

    async def delete_alert(self, alert_id: uuid.UUID) -> bool:
        return await alert_repo.delete_alert(self._session, alert_id)
