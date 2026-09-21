import uuid
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Numeric, String, func, select
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.schemas.alert import AlertCreate, AlertUpdate


class TargetPollutant(StrEnum):
    PM2_5 = "PM2.5"
    PM10 = "PM10"
    CO = "CO"
    NO2 = "NO2"
    O3 = "O3"


def round_coord(value: float) -> Decimal:
    return Decimal(str(round(value, 4)))


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    local_name: Mapped[str] = mapped_column(String(255), nullable=False)
    latitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    longitude: Mapped[Decimal] = mapped_column(Numeric(10, 7), nullable=False)
    target_pollutant: Mapped[TargetPollutant] = mapped_column(
        Enum(
            TargetPollutant,
            name="target_pollutant_enum",
            values_callable=lambda members: [member.value for member in members],
        ),
        nullable=False,
    )
    concentration_limit: Mapped[Decimal] = mapped_column(Numeric(12, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ReadingCache(Base):
    __tablename__ = "reading_cache"

    lat: Mapped[Decimal] = mapped_column(Numeric(8, 4), primary_key=True)
    lon: Mapped[Decimal] = mapped_column(Numeric(8, 4), primary_key=True)
    payload_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    aqi: Mapped[int] = mapped_column(nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )


async def list_alerts(
    session: AsyncSession,
    skip: int = 0,
    limit: int = 50,
) -> list[Alert]:
    result = await session.execute(
        select(Alert).order_by(Alert.created_at.desc()).offset(skip).limit(limit)
    )
    return list(result.scalars().all())


async def get_alert(session: AsyncSession, alert_id: uuid.UUID) -> Alert | None:
    return await session.get(Alert, alert_id)


async def create_alert(session: AsyncSession, data: AlertCreate) -> Alert:
    alert = Alert(
        local_name=data.local_name,
        latitude=data.latitude,
        longitude=data.longitude,
        target_pollutant=TargetPollutant(data.target_pollutant.value),
        concentration_limit=data.concentration_limit,
    )
    session.add(alert)
    await session.flush()
    await session.refresh(alert)
    return alert


async def update_alert(
    session: AsyncSession,
    alert_id: uuid.UUID,
    data: AlertUpdate,
) -> Alert | None:
    alert = await get_alert(session, alert_id)
    if alert is None:
        return None

    for field, value in data.model_dump(exclude_unset=True).items():
        if field == "target_pollutant" and value is not None:
            enum_value = value.value if hasattr(value, "value") else value
            setattr(alert, field, TargetPollutant(enum_value))
        else:
            setattr(alert, field, value)

    await session.flush()
    await session.refresh(alert)
    return alert


async def delete_alert(session: AsyncSession, alert_id: uuid.UUID) -> bool:
    alert = await get_alert(session, alert_id)
    if alert is None:
        return False
    await session.delete(alert)
    await session.flush()
    return True


async def get_cache(
    session: AsyncSession,
    lat: float,
    lon: float,
) -> ReadingCache | None:
    return await session.get(ReadingCache, (round_coord(lat), round_coord(lon)))


async def upsert_cache(
    session: AsyncSession,
    lat: float,
    lon: float,
    payload_json: dict,
    aqi: int,
    fetched_at: datetime,
) -> ReadingCache:
    lat_key = round_coord(lat)
    lon_key = round_coord(lon)
    stmt = (
        insert(ReadingCache)
        .values(
            lat=lat_key,
            lon=lon_key,
            payload_json=payload_json,
            aqi=aqi,
            fetched_at=fetched_at,
        )
        .on_conflict_do_update(
            index_elements=[ReadingCache.lat, ReadingCache.lon],
            set_={
                "payload_json": payload_json,
                "aqi": aqi,
                "fetched_at": fetched_at,
            },
        )
        .returning(ReadingCache)
    )
    result = await session.execute(stmt)
    cache = result.scalar_one()
    await session.flush()
    return cache
