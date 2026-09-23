from pydantic import BaseModel, Field


class GeocodeResult(BaseModel):
    name: str
    state: str | None = None
    country: str
    latitude: float
    longitude: float


class GeocodeResponse(BaseModel):
    query: str
    available: bool
    results: list[GeocodeResult] = Field(default_factory=list)
