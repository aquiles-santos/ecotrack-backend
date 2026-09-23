import json

import pytest
from app.core.config import Settings, get_settings
from app.core.security import reset_rate_limiter
from app.services.openweather_service import set_http_client
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.fixture(autouse=True)
def reset_throttle_state() -> None:
    reset_rate_limiter()
    yield
    reset_rate_limiter()


@pytest.fixture
def low_throttle_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://ecotrack:ecotrack@localhost:5432/ecotrack",
        OPENWEATHER_API_KEY="test-api-key",
        THROTTLE_RPM=2,
    )
    monkeypatch.setattr("app.core.security.get_settings", lambda: settings)
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_air_quality_returns_429_with_retry_after(
    client: AsyncClient,
    db_session: AsyncSession,
    low_throttle_settings: None,
    openweather_settings: None,
) -> None:
    from app.tests.conftest import install_openweather_mock

    mock_client, _ = install_openweather_mock()
    set_http_client(mock_client)

    for _ in range(2):
        response = await client.get(
            "/api/v1/air-quality",
            params={"lat": -23.55, "lon": -46.63},
        )
        assert response.status_code == 200

    response = await client.get(
        "/api/v1/air-quality",
        params={"lat": -23.55, "lon": -46.63},
    )
    assert response.status_code == 429
    assert response.headers.get("Retry-After") is not None
    assert int(response.headers["Retry-After"]) >= 1
    assert response.json()["detail"] == "Rate limit exceeded. Try again later."


@pytest.mark.asyncio
async def test_validation_error_has_no_traceback(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/air-quality",
        params={"lat": 999, "lon": 0},
    )
    assert response.status_code == 422
    body = response.text
    assert "Traceback" not in body
    assert "traceback" not in body.lower()


@pytest.mark.asyncio
async def test_unhandled_error_has_no_traceback(
    client: AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def boom(_self: object, lat: float, lon: float) -> None:
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(
        "app.services.openweather_service.OpenWeatherService.get_air_quality",
        boom,
    )

    response = await client.get(
        "/api/v1/air-quality",
        params={"lat": -23.55, "lon": -46.63},
    )
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_request_logging_emits_json_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    capsys: pytest.CaptureFixture[str],
) -> None:
    await client.get("/api/v1/alerts")

    captured = capsys.readouterr()
    log_line = captured.out.strip().splitlines()[-1]
    payload = json.loads(log_line)

    assert payload["level"] == "info"
    assert payload["route"] == "/api/v1/alerts"
    assert payload["status_code"] == 200
    assert "correlation_id" in payload
    assert "latency_ms" in payload
    assert "timestamp" in payload
