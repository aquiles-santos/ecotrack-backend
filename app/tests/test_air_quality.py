from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from app.core.config import get_settings
from app.models import alert as alert_repo
from app.models.alert import CACHE_TTL, ReadingCache, is_cache_fresh, round_coord
from app.schemas.air_quality import (
    AirQualityQuery,
    AirQualityResponse,
    AirQualitySource,
)
from app.services.openweather_service import (
    OPENWEATHER_RETRY_ATTEMPTS,
    calculate_aqi,
    get_circuit_breaker,
    parse_components,
    parse_openweather_payload,
    set_http_client,
)
from app.tests.conftest import install_openweather_mock, open_circuit_with_failures
from httpx import AsyncClient
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession


def test_calculate_aqi_from_pm2_5_good() -> None:
    pollutants = parse_components({"pm2_5": 5.0})
    assert calculate_aqi(pollutants) == 1


def test_calculate_aqi_from_pm2_5_fair() -> None:
    pollutants = parse_components({"pm2_5": 15.0})
    assert calculate_aqi(pollutants) == 2


def test_calculate_aqi_uses_worst_pollutant() -> None:
    pollutants = parse_components({"pm2_5": 5.0, "pm10": 120.0})
    assert calculate_aqi(pollutants) == 4


def test_calculate_aqi_returns_one_when_no_pollutants() -> None:
    assert calculate_aqi(parse_components({})) == 1


def test_parse_openweather_payload_raises_on_empty_list() -> None:
    with pytest.raises(ValueError, match="missing list data"):
        parse_openweather_payload({"list": []})


def test_unavailable_fallback_rejects_numeric_aqi() -> None:
    with pytest.raises(ValidationError, match="aqi must be absent"):
        AirQualityResponse(
            lat=0.0,
            lon=0.0,
            pollutants=parse_components({}),
            aqi=1,
            source=AirQualitySource.UNAVAILABLE_FALLBACK,
            fetched_at=datetime(2026, 3, 21, tzinfo=UTC),
        )


def test_measured_air_quality_requires_aqi() -> None:
    with pytest.raises(ValidationError, match="aqi is required"):
        AirQualityResponse(
            lat=0.0,
            lon=0.0,
            pollutants=parse_components({"pm2_5": 5.0}),
            aqi=None,
            source=AirQualitySource.OPENWEATHER,
            fetched_at=datetime(2026, 3, 21, tzinfo=UTC),
        )


def test_air_quality_query_rejects_invalid_coordinates() -> None:
    with pytest.raises(ValidationError):
        AirQualityQuery(lat=91.0, lon=0.0)
    with pytest.raises(ValidationError):
        AirQualityQuery(lat=0.0, lon=181.0)


def test_round_coord_normalizes_to_four_decimals() -> None:
    assert round_coord(-23.55051234) == Decimal("-23.5505")
    assert round_coord(46.6333789) == Decimal("46.6334")


def test_is_cache_fresh_within_ttl() -> None:
    now = datetime(2026, 3, 21, 12, 0, tzinfo=UTC)
    cache = ReadingCache(
        lat=Decimal("-23.5505"),
        lon=Decimal("-46.6333"),
        payload_json={},
        aqi=1,
        fetched_at=now - CACHE_TTL + timedelta(seconds=1),
    )
    assert is_cache_fresh(cache, now=now) is True


def test_is_cache_fresh_expired_at_boundary() -> None:
    now = datetime(2026, 3, 21, 12, 0, tzinfo=UTC)
    cache = ReadingCache(
        lat=Decimal("-23.5505"),
        lon=Decimal("-46.6333"),
        payload_json={},
        aqi=1,
        fetched_at=now - CACHE_TTL - timedelta(seconds=1),
    )
    assert is_cache_fresh(cache, now=now) is False


@pytest.mark.asyncio
async def test_get_air_quality_returns_standardized_response(
    client: AsyncClient,
    openweather_settings: None,
) -> None:
    mock_client, requests = install_openweather_mock()
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
    assert body["stale"] is False
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
async def test_get_air_quality_returns_fresh_cache_without_http_call(
    client: AsyncClient,
    db_session: AsyncSession,
    openweather_settings: None,
) -> None:
    mock_client, requests = install_openweather_mock(
        response=httpx.Response(500),
    )

    await alert_repo.upsert_cache(
        db_session,
        lat=-23.5505,
        lon=-46.6333,
        payload_json={"pollutants": {"pm2_5": 12.5, "pm10": 20.0}},
        aqi=2,
        fetched_at=datetime.now(UTC),
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
    assert body["stale"] is False
    assert body["pollutants"]["pm2_5"] == 12.5
    assert body["aqi"] == 2
    assert len(requests) == 0


@pytest.mark.asyncio
async def test_get_air_quality_second_request_uses_cache_without_http(
    client: AsyncClient,
    openweather_settings: None,
) -> None:
    mock_client, requests = install_openweather_mock()
    params = {"lat": -23.5505, "lon": -46.6333}

    try:
        first = await client.get("/api/v1/air-quality", params=params)
        second = await client.get("/api/v1/air-quality", params=params)
    finally:
        await mock_client.aclose()
        set_http_client(None)
        get_settings.cache_clear()

    assert first.status_code == 200
    assert first.json()["source"] == "openweather"
    assert second.status_code == 200
    assert second.json()["source"] == "cache"
    assert second.json()["stale"] is False
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_get_air_quality_expired_cache_refreshes_from_openweather(
    client: AsyncClient,
    db_session: AsyncSession,
    openweather_settings: None,
) -> None:
    mock_client, requests = install_openweather_mock()

    await alert_repo.upsert_cache(
        db_session,
        lat=-23.5505,
        lon=-46.6333,
        payload_json={"pollutants": {"pm2_5": 99.0}},
        aqi=5,
        fetched_at=datetime.now(UTC) - timedelta(minutes=11),
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
    assert body["source"] == "openweather"
    assert body["pollutants"]["pm2_5"] == 4.33
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_get_air_quality_retries_before_failing(
    client: AsyncClient,
    openweather_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[float] = []

    async def fast_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        "app.services.openweather_service.asyncio.sleep",
        fast_sleep,
    )

    mock_client, requests = install_openweather_mock(
        side_effect=httpx.TimeoutException("timeout"),
    )

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
    assert body["source"] == "unavailable_fallback"
    assert body["aqi"] is None
    assert body["stale"] is False
    assert get_circuit_breaker().current_state == "open"
    assert len(requests) == OPENWEATHER_RETRY_ATTEMPTS
    assert sleep_calls == [0.5, 1.0]


@pytest.mark.asyncio
async def test_get_air_quality_open_circuit_skips_http_and_returns_stale_cache(
    client: AsyncClient,
    db_session: AsyncSession,
    openweather_settings: None,
) -> None:
    mock_client, requests = install_openweather_mock(
        side_effect=httpx.TimeoutException("timeout"),
    )

    try:
        await open_circuit_with_failures(client)
        requests.clear()

        await alert_repo.upsert_cache(
            db_session,
            lat=-23.5505,
            lon=-46.6333,
            payload_json={"pollutants": {"pm2_5": 8.0}},
            aqi=1,
            fetched_at=datetime.now(UTC) - timedelta(minutes=11),
        )
        await db_session.flush()

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
    assert body["stale"] is True
    assert body["pollutants"]["pm2_5"] == 8.0
    assert len(requests) == 0


@pytest.mark.asyncio
async def test_get_air_quality_circuit_recovers_after_reset_timeout(
    client: AsyncClient,
    openweather_settings: None,
) -> None:
    breaker = get_circuit_breaker()
    original_reset_timeout = breaker.reset_timeout
    breaker.reset_timeout = 0

    failure_client, _requests = install_openweather_mock(
        side_effect=httpx.TimeoutException("timeout"),
    )
    success_client: httpx.AsyncClient | None = None

    try:
        await open_circuit_with_failures(client)
        await failure_client.aclose()

        success_client, requests = install_openweather_mock()
        response = await client.get(
            "/api/v1/air-quality",
            params={"lat": -23.5505, "lon": -46.6333},
        )
    finally:
        breaker.reset_timeout = original_reset_timeout
        await failure_client.aclose()
        if success_client is not None:
            await success_client.aclose()
        set_http_client(None)
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.json()["source"] == "openweather"
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_get_air_quality_unavailable_without_cache_returns_fallback(
    client: AsyncClient,
    openweather_settings: None,
) -> None:
    mock_client, _requests = install_openweather_mock(
        side_effect=httpx.TimeoutException("timeout"),
    )

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
    assert body["source"] == "unavailable_fallback"
    assert body["stale"] is False
    assert body["aqi"] is None
    assert body["lat"] == -23.5505
    assert body["lon"] == -46.6333
    assert "Traceback" not in response.text
