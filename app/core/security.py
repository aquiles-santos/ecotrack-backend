"""Security helpers — authentication is out of MVP scope."""

from app.core.config import get_settings


def get_cors_origins() -> list[str]:
    return get_settings().cors_origins_list
