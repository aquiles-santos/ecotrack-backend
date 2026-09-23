import asyncio
from datetime import UTC, datetime, timedelta

import httpx
import pybreaker

from app.schemas.geocode import GeocodeResponse, GeocodeResult

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
GEOCODE_TIMEOUT = 3.0
GEOCODE_RETRY_ATTEMPTS = 3
GEOCODE_RETRY_BACKOFF_SECONDS = 0.5

GEOCODE_ERRORS = (httpx.HTTPError, ValueError, httpx.TimeoutException)


class _GeocodeTimestampListener(pybreaker.CircuitBreakerListener):
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
_geocode_listener = _GeocodeTimestampListener()
_geocode_breaker = pybreaker.CircuitBreaker(
    fail_max=3,
    reset_timeout=30,
    name="open_meteo_geocode",
)
_geocode_breaker.add_listener(_geocode_listener)


def set_http_client(client: httpx.AsyncClient | None) -> None:
    global _http_client
    _http_client = client


def get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None:
        _http_client = httpx.AsyncClient(timeout=GEOCODE_TIMEOUT)
    return _http_client


def get_circuit_breaker() -> pybreaker.CircuitBreaker:
    return _geocode_breaker


def reset_circuit_breaker() -> None:
    _geocode_breaker.close()


def _ensure_circuit_allows_call(breaker: pybreaker.CircuitBreaker) -> None:
    if breaker.current_state != "open":
        return

    opened_at = _geocode_listener.opened_at
    if opened_at is None:
        raise pybreaker.CircuitBreakerError("Open-Meteo geocode circuit open")

    if datetime.now(UTC) < opened_at + timedelta(seconds=breaker.reset_timeout):
        raise pybreaker.CircuitBreakerError("Open-Meteo geocode circuit open")

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


def parse_open_meteo_payload(data: dict) -> list[GeocodeResult]:
    raw_results = data.get("results") or []
    results: list[GeocodeResult] = []

    for entry in raw_results:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        country = entry.get("country")
        latitude = entry.get("latitude")
        longitude = entry.get("longitude")
        if (
            not isinstance(name, str)
            or not isinstance(country, str)
            or latitude is None
            or longitude is None
        ):
            continue
        results.append(
            GeocodeResult(
                name=name,
                state=entry.get("admin1"),
                country=country,
                latitude=float(latitude),
                longitude=float(longitude),
            )
        )

    return results


class GeocodeService:
    async def geocode(self, query: str, limit: int) -> GeocodeResponse:
        try:
            results = await self._fetch_with_resilience(query, limit)
        except (pybreaker.CircuitBreakerError, *GEOCODE_ERRORS):
            return GeocodeResponse(query=query, available=False, results=[])

        return GeocodeResponse(query=query, available=True, results=results)

    async def _fetch_with_resilience(
        self,
        query: str,
        limit: int,
    ) -> list[GeocodeResult]:
        breaker = get_circuit_breaker()
        _ensure_circuit_allows_call(breaker)

        last_exc: Exception | None = None
        for attempt in range(GEOCODE_RETRY_ATTEMPTS):
            try:
                result = await self._fetch_from_open_meteo(query, limit)
            except GEOCODE_ERRORS as exc:
                last_exc = exc
                try:
                    _record_failure(exc)
                except pybreaker.CircuitBreakerError:
                    raise
                if attempt < GEOCODE_RETRY_ATTEMPTS - 1:
                    await asyncio.sleep(
                        GEOCODE_RETRY_BACKOFF_SECONDS * (2**attempt)
                    )
                continue

            _record_success()
            return result

        if last_exc is None:
            raise RuntimeError("Open-Meteo geocode fetch failed without exception")
        raise last_exc

    async def _fetch_from_open_meteo(
        self,
        query: str,
        limit: int,
    ) -> list[GeocodeResult]:
        client = get_http_client()
        response = await client.get(
            GEOCODE_URL,
            params={
                "name": query,
                "count": limit,
            },
        )
        response.raise_for_status()
        return parse_open_meteo_payload(response.json())


def _reraise(exc: Exception) -> None:
    raise exc
