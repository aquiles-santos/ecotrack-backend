import httpx
import pytest
from app.services.geocode_service import (
    GEOCODE_RETRY_ATTEMPTS,
    get_circuit_breaker,
    parse_open_meteo_payload,
    set_http_client,
)
from app.services.openweather_service import (
    get_circuit_breaker as get_openweather_circuit_breaker,
)
from app.tests.conftest import (
    install_geocode_mock,
    install_openweather_mock,
    open_geocode_circuit_with_failures,
)
from httpx import AsyncClient


def test_parse_open_meteo_payload_maps_admin1_to_state() -> None:
    results = parse_open_meteo_payload(
        {
            "results": [
                {
                    "name": "São Paulo",
                    "admin1": "São Paulo",
                    "country": "Brazil",
                    "latitude": -23.5475,
                    "longitude": -46.6361,
                }
            ]
        }
    )

    assert len(results) == 1
    assert results[0].name == "São Paulo"
    assert results[0].state == "São Paulo"
    assert results[0].country == "Brazil"
    assert results[0].latitude == -23.5475
    assert results[0].longitude == -46.6361


def test_parse_open_meteo_payload_returns_empty_list_without_results() -> None:
    assert parse_open_meteo_payload({}) == []
    assert parse_open_meteo_payload({"results": []}) == []


@pytest.mark.asyncio
async def test_get_geocode_returns_normalized_results(client: AsyncClient) -> None:
    mock_client, requests = install_geocode_mock()

    try:
        response = await client.get(
            "/api/v1/geocode",
            params={"q": "São Paulo", "limit": 2},
        )
    finally:
        await mock_client.aclose()
        set_http_client(None)

    assert response.status_code == 200
    body = response.json()
    assert body["query"] == "São Paulo"
    assert body["available"] is True
    assert len(body["results"]) == 2
    assert body["results"][0]["name"] == "São Paulo"
    assert body["results"][0]["state"] == "São Paulo"
    assert body["results"][0]["country"] == "Brazil"
    assert "appid" not in response.text
    assert "api_key" not in response.text
    assert len(requests) == 1
    assert requests[0].url.params["name"] == "São Paulo"
    assert requests[0].url.params["count"] == "2"


@pytest.mark.asyncio
async def test_get_geocode_empty_results_stays_available(client: AsyncClient) -> None:
    mock_client, requests = install_geocode_mock(
        response=httpx.Response(200, json={"results": []}),
    )

    try:
        response = await client.get(
            "/api/v1/geocode",
            params={"q": "xyznonexistent"},
        )
    finally:
        await mock_client.aclose()
        set_http_client(None)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["results"] == []
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_get_geocode_invalid_query_returns_422(client: AsyncClient) -> None:
    response = await client.get("/api/v1/geocode", params={"q": ""})

    assert response.status_code == 422
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_get_geocode_invalid_limit_returns_422(client: AsyncClient) -> None:
    response = await client.get(
        "/api/v1/geocode",
        params={"q": "São Paulo", "limit": 10},
    )

    assert response.status_code == 422
    assert "Traceback" not in response.text


@pytest.mark.asyncio
async def test_get_geocode_retries_before_unavailable(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sleep_calls: list[float] = []

    async def fast_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(
        "app.services.geocode_service.asyncio.sleep",
        fast_sleep,
    )

    mock_client, requests = install_geocode_mock(
        side_effect=httpx.TimeoutException("timeout"),
    )

    try:
        response = await client.get(
            "/api/v1/geocode",
            params={"q": "São Paulo"},
        )
    finally:
        await mock_client.aclose()
        set_http_client(None)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["results"] == []
    assert get_circuit_breaker().current_state == "open"
    assert len(requests) == GEOCODE_RETRY_ATTEMPTS
    assert sleep_calls == [0.5, 1.0]


@pytest.mark.asyncio
async def test_get_geocode_open_circuit_skips_http(client: AsyncClient) -> None:
    mock_client, requests = install_geocode_mock(
        side_effect=httpx.TimeoutException("timeout"),
    )

    try:
        await open_geocode_circuit_with_failures(client)
        requests.clear()

        response = await client.get(
            "/api/v1/geocode",
            params={"q": "São Paulo"},
        )
    finally:
        await mock_client.aclose()
        set_http_client(None)

    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["results"] == []
    assert len(requests) == 0


@pytest.mark.asyncio
async def test_geocode_circuit_open_does_not_affect_openweather(
    client: AsyncClient,
    openweather_settings: None,
) -> None:
    geocode_client, _ = install_geocode_mock(
        side_effect=httpx.TimeoutException("timeout"),
    )
    openweather_client, openweather_requests = install_openweather_mock()

    try:
        await open_geocode_circuit_with_failures(client)
        assert get_circuit_breaker().current_state == "open"
        assert get_openweather_circuit_breaker().current_state == "closed"

        response = await client.get(
            "/api/v1/air-quality",
            params={"lat": -23.5505, "lon": -46.6333},
        )
    finally:
        await geocode_client.aclose()
        await openweather_client.aclose()
        set_http_client(None)

    assert response.status_code == 200
    assert response.json()["source"] == "openweather"
    assert len(openweather_requests) == 1


@pytest.mark.asyncio
async def test_geocode_is_not_throttled_when_air_quality_is(
    client: AsyncClient,
    openweather_settings: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.core.config import Settings, get_settings
    from app.core.security import reset_rate_limiter

    settings = Settings(
        DATABASE_URL="postgresql+asyncpg://ecotrack:ecotrack@localhost:5432/ecotrack",
        OPENWEATHER_API_KEY="test-api-key",
        THROTTLE_RPM=1,
    )
    monkeypatch.setattr("app.core.security.get_settings", lambda: settings)
    get_settings.cache_clear()
    reset_rate_limiter()

    geocode_client, geocode_requests = install_geocode_mock()
    openweather_client, _ = install_openweather_mock()

    try:
        throttled = await client.get(
            "/api/v1/air-quality",
            params={"lat": -23.5505, "lon": -46.6333},
        )
        assert throttled.status_code == 200

        blocked = await client.get(
            "/api/v1/air-quality",
            params={"lat": -23.5505, "lon": -46.6333},
        )
        assert blocked.status_code == 429

        geocode_response = await client.get(
            "/api/v1/geocode",
            params={"q": "São Paulo"},
        )
    finally:
        await geocode_client.aclose()
        await openweather_client.aclose()
        set_http_client(None)
        get_settings.cache_clear()

    assert geocode_response.status_code == 200
    assert geocode_response.json()["available"] is True
    assert len(geocode_requests) == 1
