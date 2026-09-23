import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pybreaker
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import alert as alert_repo
from app.schemas.air_quality import (
    AirQualityResponse,
    AirQualitySource,
    Pollutants,
)

OPENWEATHER_URL = "https://api.openweathermap.org/data/2.5/air_pollution"
OPENWEATHER_TIMEOUT = 3.0
OPENWEATHER_RETRY_ATTEMPTS = 3
OPENWEATHER_RETRY_BACKOFF_SECONDS = 0.5

PM25_THRESHOLDS = (10.0, 25.0, 50.0, 75.0)
PM10_THRESHOLDS = (20.0, 50.0, 100.0, 200.0)
NO2_THRESHOLDS = (40.0, 70.0, 150.0, 200.0)
O3_THRESHOLDS = (60.0, 100.0, 140.0, 180.0)
CO_THRESHOLDS = (4400.0, 9400.0, 12400.0, 15400.0)

OPENWEATHER_ERRORS = (httpx.HTTPError, ValueError, httpx.TimeoutException)


class _OpenTimestampListener(pybreaker.CircuitBreakerListener):
    """Guarda o instante em que o circuito abre, via listener público.

    O half-open continua sendo o reset_timeout do pybreaker. Não lemos
    o estado interno da biblioteca para decidir se a chamada está bloqueada.
    """

    def __init__(self) -> None:
        self.opened_at: datetime | None = None

    def state_change(
        self,
        cb: pybreaker.CircuitBreaker,
        old_state: pybreaker.CircuitBreakerState | None,
        new_state: pybreaker.CircuitBreakerState,
    ) -> None:
        if new_state.name == "open":
            self.opened_at = datetime.now(UTC)
        else:
            self.opened_at = None


_http_client: httpx.AsyncClient | None = None
_open_listener = _OpenTimestampListener()
_openweather_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=30,
    name="openweather",
)
_openweather_breaker.add_listener(_open_listener)


def set_http_client(client: httpx.AsyncClient | None) -> None:
    global _http_client
    _http_client = client


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=OPENWEATHER_TIMEOUT)
    return _http_client


def get_circuit_breaker() -> pybreaker.CircuitBreaker:
    return _openweather_breaker


def reset_circuit_breaker() -> None:
    _openweather_breaker.close()


def _ensure_circuit_allows_call(breaker: pybreaker.CircuitBreaker) -> None:
    if breaker.current_state != "open":
        return

    opened_at = _open_listener.opened_at
    if opened_at is None:
        raise pybreaker.CircuitBreakerError("OpenWeather circuit open")

    if datetime.now(UTC) < opened_at + timedelta(seconds=breaker.reset_timeout):
        raise pybreaker.CircuitBreakerError("OpenWeather circuit open")

    breaker.half_open()


def _record_failure(exc: Exception) -> None:
    try:
        get_circuit_breaker().call(_reraise, exc)
    except pybreaker.CircuitBreakerError:
        raise
    except Exception:
        return


def _record_success() -> None:
    get_circuit_breaker().call(lambda: None)


def _pollutant_level(value: float, thresholds: tuple[float, ...]) -> int:
    for level, threshold in enumerate(thresholds, start=1):
        if value < threshold:
            return level
    return 5


def calculate_aqi(pollutants: Pollutants) -> int:
    levels: list[int] = []
    if pollutants.pm2_5 is not None:
        levels.append(_pollutant_level(pollutants.pm2_5, PM25_THRESHOLDS))
    if pollutants.pm10 is not None:
        levels.append(_pollutant_level(pollutants.pm10, PM10_THRESHOLDS))
    if pollutants.no2 is not None:
        levels.append(_pollutant_level(pollutants.no2, NO2_THRESHOLDS))
    if pollutants.o3 is not None:
        levels.append(_pollutant_level(pollutants.o3, O3_THRESHOLDS))
    if pollutants.co is not None:
        levels.append(_pollutant_level(pollutants.co, CO_THRESHOLDS))
    return max(levels) if levels else 1


def parse_components(raw: dict) -> Pollutants:
    return Pollutants(
        pm2_5=raw.get("pm2_5"),
        pm10=raw.get("pm10"),
        co=raw.get("co"),
        no2=raw.get("no2"),
        o3=raw.get("o3"),
    )


def parse_openweather_payload(data: dict) -> tuple[Pollutants, datetime]:
    if not data.get("list"):
        raise ValueError("OpenWeather response missing list data")

    entry = data["list"][0]
    components = entry.get("components") or {}
    pollutants = parse_components(components)
    fetched_at = datetime.fromtimestamp(entry["dt"], tz=UTC)
    return pollutants, fetched_at


def pollutants_to_payload(pollutants: Pollutants) -> dict:
    return {
        "pollutants": pollutants.model_dump(),
    }


def cache_to_response(
    cache: alert_repo.ReadingCache,
    lat: float,
    lon: float,
    *,
    stale: bool = False,
) -> AirQualityResponse:
    payload = cache.payload_json
    raw = payload.get("pollutants") or payload.get("components") or {}
    pollutants = parse_components(raw) if isinstance(raw, dict) else Pollutants()
    return AirQualityResponse(
        lat=lat,
        lon=lon,
        pollutants=pollutants,
        aqi=cache.aqi,
        source=AirQualitySource.CACHE,
        fetched_at=cache.fetched_at,
        stale=stale,
    )


class OpenWeatherService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_air_quality(self, lat: float, lon: float) -> AirQualityResponse:
        cache = await alert_repo.get_cache(self._session, lat, lon)
        if cache is not None and alert_repo.is_cache_fresh(cache):
            return cache_to_response(cache, lat, lon)

        settings = get_settings()
        if not settings.openweather_api_key:
            return self._fallback_or_unavailable(cache, lat, lon)

        try:
            pollutants, fetched_at = await self._fetch_with_resilience(lat, lon)
        except (pybreaker.CircuitBreakerError, *OPENWEATHER_ERRORS):
            return self._fallback_or_unavailable(cache, lat, lon)

        aqi = calculate_aqi(pollutants)
        await alert_repo.upsert_cache(
            self._session,
            lat=lat,
            lon=lon,
            payload_json=pollutants_to_payload(pollutants),
            aqi=aqi,
            fetched_at=fetched_at,
        )

        return AirQualityResponse(
            lat=lat,
            lon=lon,
            pollutants=pollutants,
            aqi=aqi,
            source=AirQualitySource.OPENWEATHER,
            fetched_at=fetched_at,
        )

    def _fallback_or_unavailable(
        self,
        cache: alert_repo.ReadingCache | None,
        lat: float,
        lon: float,
    ) -> AirQualityResponse:
        if cache is not None:
            return cache_to_response(cache, lat, lon, stale=True)

        return AirQualityResponse(
            lat=lat,
            lon=lon,
            pollutants=Pollutants(),
            aqi=None,
            source=AirQualitySource.UNAVAILABLE_FALLBACK,
            fetched_at=datetime.now(UTC),
            stale=False,
        )

    async def _fetch_with_resilience(
        self,
        lat: float,
        lon: float,
    ) -> tuple[Pollutants, datetime]:
        breaker = get_circuit_breaker()
        _ensure_circuit_allows_call(breaker)

        last_exc: Exception | None = None
        for attempt in range(OPENWEATHER_RETRY_ATTEMPTS):
            try:
                result = await self._fetch_from_openweather(lat, lon)
            except OPENWEATHER_ERRORS as exc:
                last_exc = exc
                try:
                    _record_failure(exc)
                except pybreaker.CircuitBreakerError:
                    raise
                if attempt < OPENWEATHER_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(
                        OPENWEATHER_RETRY_BACKOFF_SECONDS * (2**attempt)
                    )
                continue

            _record_success()
            return result

        if last_exc is None:
            raise RuntimeError("OpenWeather fetch failed without exception")
        raise last_exc

    async def _fetch_from_openweather(
        self,
        lat: float,
        lon: float,
    ) -> tuple[Pollutants, datetime]:
        settings = get_settings()
        client = get_http_client()
        response = await client.get(
            OPENWEATHER_URL,
            params={
                "lat": lat,
                "lon": lon,
                "appid": settings.openweather_api_key,
            },
        )
        response.raise_for_status()
        return parse_openweather_payload(response.json())


def _reraise(exc: Exception) -> None:
    raise exc
