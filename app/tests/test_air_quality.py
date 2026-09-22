from datetime import UTC, datetime

import httpx
import pytest
from app.core.config import Settings, get_settings
from app.models import alert as alert_repo
from app.services.openweather_service import (
    calculate_aqi,
    parse_components,
    set_http_client,
)
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

OPENWEATHER_RESPONSE = {
    "coord": {"lon": -46.6333, "lat": -23.5505},
    "list": [
        {
            "dt": 1605182400,
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


def test_calculate_aqi_from_pm2_5_good() -> None:
    pollutants = parse_components({"pm2_5": 5.0})
    assert calculate_aqi(pollutants) == 1


def test_calculate_aqi_from_pm2_5_fair() -> None:
    pollutants = parse_components({"pm2_5": 15.0})
    assert calculate_aqi(pollutants) == 2


def test_calculate_aqi_uses_worst_pollutant() -> None:
    pollutants = parse_components({"pm2_5": 5.0, "pm10": 120.0})
    assert calculate_aqi(pollutants) == 4


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


def _install_openweather_mock(
    *,
    response: httpx.Response | None = None,
) -> tuple[httpx.AsyncClient, list[httpx.Request]]:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert "appid=test-api-key" in str(request.url)
        return response or httpx.Response(200, json=OPENWEATHER_RESPONSE)

    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        timeout=3.0,
    )
    set_http_client(client)
    return client, requests


@pytest.mark.asyncio
async def test_get_air_quality_returns_standardized_response(
    client: AsyncClient,
    openweather_settings: None,
) -> None:
    mock_client, requests = _install_openweather_mock()
    try:
        response = await client.get(
            "/api/v1/air-quality",
            params={"lat": -23.5505, "lon": -46.6333},
        )
    finally:
        await mock_client.aclose()
        set_http_client(None)
        get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["lat"] == -23.5505
    assert body["lon"] == -46.6333
    assert body["pollutants"]["pm2_5"] == 4.33
    assert body["pollutants"]["pm10"] == 8.04
    assert body["aqi"] == 1
    assert body["source"] == "openweather"
    assert "fetched_at" in body
    assert "appid" not in response.text
    assert "test-api-key" not in response.text
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_get_air_quality_invalid_lat_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/air-quality",
        params={"lat": 95.0, "lon": -46.6333},
    )

    assert response.status_code == 422
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_get_air_quality_invalid_lon_returns_422(
    client: AsyncClient,
) -> None:
    response = await client.get(
        "/api/v1/air-quality",
        params={"lat": -23.5505, "lon": 200.0},
    )

    assert response.status_code == 422
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_get_air_quality_returns_cache_without_http_call(
    client: AsyncClient,
    db_session: AsyncSession,
    openweather_settings: None,
) -> None:
    mock_client, requests = _install_openweather_mock(
        response=httpx.Response(500),
    )

    await alert_repo.upsert_cache(
        db_session,
        lat=-23.5505,
        lon=-46.6333,
        payload_json={"pollutants": {"pm2_5": 12.5, "pm10": 20.0}},
        aqi=2,
        fetched_at=datetime(2026, 3, 21, 12, 0, tzinfo=UTC),
    )
    await db_session.flush()

    try:
        response = await client.get(
            "/api/v1/air-quality",
            params={"lat": -23.5505, "lon": -46.6333},
        )
    finally:
        await mock_client.aclose()
        set_http_client(None)
        get_settings.cache_clear()

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "cache"
    assert body["pollutants"]["pm2_5"] == 12.5
    assert body["aqi"] == 2
    assert len(requests) == 0
