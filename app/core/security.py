"""Security helpers — authentication is out of MVP scope."""

import asyncio
import time
from collections import defaultdict

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

_window_seconds = 60


class _IpRateLimiter:
    def __init__(self) -> None:
        self._requests: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def check(self, client_ip: str, limit: int) -> tuple[bool, int]:
        async with self._lock:
            now = time.monotonic()
            window_start = now - _window_seconds
            timestamps = self._requests[client_ip]
            timestamps[:] = [t for t in timestamps if t > window_start]

            if len(timestamps) >= limit:
                oldest = timestamps[0]
                retry_after = int(_window_seconds - (now - oldest)) + 1
                return False, max(retry_after, 1)

            timestamps.append(now)
            return True, 0

    def reset(self) -> None:
        self._requests.clear()


_rate_limiter = _IpRateLimiter()


def reset_rate_limiter() -> None:
    """Reset in-memory counters (used in tests)."""
    _rate_limiter.reset()


def get_cors_origins() -> list[str]:
    return get_settings().cors_origins_list


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client is not None:
        return request.client.host
    return "unknown"


async def enforce_air_quality_throttle(request: Request) -> None:
    """Aplica THROTTLE_RPM neste processo.

    O contador fica em memória. Vários workers do Uvicorn não compartilham
    a cota: cada processo permite até THROTTLE_RPM requisições por minuto.
    """
    settings = get_settings()
    allowed, retry_after = await _rate_limiter.check(
        _client_ip(request),
        settings.throttle_rpm,
    )
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Try again later.",
            headers={"Retry-After": str(retry_after)},
        )
