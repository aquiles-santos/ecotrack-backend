from collections.abc import AsyncGenerator, Generator
from datetime import UTC, datetime

import httpx
import pytest
import pytest_asyncio
from app.core.config import Settings, get_settings
from app.core.database import Base, get_session
from app.main import app
from app.models.alert import Alert, ReadingCache
from app.services.openweather_service import (
    get_circuit_breaker,
    reset_circuit_breaker,
    set_http_client,
)
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

OPENWEATHER_RESPONSE = {
    "coord": {"lon": -46.6333, "lat": -23.5505},
    "list": [
        {
            "dt": int(datetime.now(UTC).timestamp()),
            "main": {"aqi": 2},
            "components": {
                "co": 261.09,
                "no": 0.03,
                "no2": 0.87,
                "o3": 36.92,
                "so2": 0.65,
                "pm2_5": 4.33,
                "pm10": 8.04,
                "nh3": 1.85,
            },
        }
    ],
}


def install_openweather_mock(
    *,
    response: httpx.Response | None = None,
    side_effect: Exception | None = None,
) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "appid=test-api-key" in str(request.url)
        if side_effect is not None:
            raise side_effect
        return response or httpx.Response(200, json=OPENWEATHER_RESPONSE)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=3.0,
    )
    set_http_client(client)
    return client, requests


async def open_circuit_with_failures(
    client: AsyncClient,
    *,
    lat: float = -23.5505,
    lon: float = -46.6333,
) -> None:
    for _ in range(3):
        response = await client.get(
            "/api/v1/air-quality",
            params={"lat": lat, "lon": lon},
        )
        assert response.status_code == 200
        assert response.json()["source"] == "unavailable_fallback"

    assert get_circuit_breaker().current_state == "open"


@pytest.fixture
def openweather_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://ecotrack:ecotrack@localhost:5432/ecotrack",
        OPENWEATHER_API_KEY="test-api-key",
    )
    monkeypatch.setattr(
        "app.services.openweather_service.get_settings",
        lambda: settings,
    )
    get_settings.cache_clear()


@pytest.fixture(autouse=True)
def reset_openweather_state() -> Generator[None, None, None]:
    reset_circuit_breaker()
    set_http_client(None)
    yield
    reset_circuit_breaker()
    set_http_client(None)


@pytest_asyncio.fixture
async def test_engine() -> AsyncGenerator[AsyncEngine, None]:
    settings = get_settings()
    engine = create_async_engine(
        settings.database_url,
        poolclass=NullPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(
    test_engine: AsyncEngine,
) -> AsyncGenerator[AsyncSession, None]:
    async with test_engine.connect() as connection:
        transaction = await connection.begin()
        session = AsyncSession(
            bind=connection,
            join_transaction_mode="create_savepoint",
            expire_on_commit=False,
        )

        async def override_get_session() -> AsyncGenerator[AsyncSession, None]:
            yield session

        app.dependency_overrides[get_session] = override_get_session

        await session.execute(delete(ReadingCache))
        await session.execute(delete(Alert))
        await session.flush()

        try:
            yield session
        finally:
            app.dependency_overrides.clear()
            await session.close()
            await transaction.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as http_client:
        yield http_client
