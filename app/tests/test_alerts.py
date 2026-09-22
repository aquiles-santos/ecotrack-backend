from datetime import UTC, datetime

import pytest
from app.models import alert as alert_repo
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

ALERT_PAYLOAD = {
    "local_name": "Centro",
    "latitude": -23.5505,
    "longitude": -46.6333,
    "target_pollutant": "PM2.5",
    "concentration_limit": 25.0,
}


@pytest.mark.asyncio
async def test_create_alert_returns_201(client: AsyncClient) -> None:
    response = await client.post("/api/v1/alerts", json=ALERT_PAYLOAD)

    assert response.status_code == 201
    body = response.json()
    assert body["local_name"] == ALERT_PAYLOAD["local_name"]
    assert body["target_pollutant"] == "PM2.5"
    assert body["latest_reading"] is None
    assert body["criticality"] is None
    assert "id" in body


@pytest.mark.asyncio
async def test_list_alerts_returns_created_alert(client: AsyncClient) -> None:
    await client.post("/api/v1/alerts", json=ALERT_PAYLOAD)

    response = await client.get("/api/v1/alerts")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["local_name"] == ALERT_PAYLOAD["local_name"]


@pytest.mark.asyncio
async def test_update_alert_returns_200(client: AsyncClient) -> None:
    create_response = await client.post("/api/v1/alerts", json=ALERT_PAYLOAD)
    alert_id = create_response.json()["id"]

    response = await client.put(
        f"/api/v1/alerts/{alert_id}",
        json={"local_name": "Vila Mariana"},
    )

    assert response.status_code == 200
    assert response.json()["local_name"] == "Vila Mariana"


@pytest.mark.asyncio
async def test_delete_alert_returns_204(client: AsyncClient) -> None:
    create_response = await client.post("/api/v1/alerts", json=ALERT_PAYLOAD)
    alert_id = create_response.json()["id"]

    response = await client.delete(f"/api/v1/alerts/{alert_id}")

    assert response.status_code == 204
    assert response.content == b""


@pytest.mark.asyncio
async def test_update_missing_alert_returns_404_without_traceback(
    client: AsyncClient,
) -> None:
    response = await client.put(
        "/api/v1/alerts/00000000-0000-0000-0000-000000000000",
        json={"local_name": "Inexistente"},
    )

    assert response.status_code == 404
    body = response.text
    assert "Alert not found" in body
    assert "Traceback" not in body


@pytest.mark.asyncio
async def test_delete_missing_alert_returns_404_without_traceback(
    client: AsyncClient,
) -> None:
    response = await client.delete(
        "/api/v1/alerts/00000000-0000-0000-0000-000000000000",
    )

    assert response.status_code == 404
    body = response.text
    assert "Alert not found" in body
    assert "Traceback" not in body


@pytest.mark.asyncio
async def test_list_alerts_pagination(client: AsyncClient) -> None:
    for index in range(3):
        payload = {**ALERT_PAYLOAD, "local_name": f"Local {index}"}
        await client.post("/api/v1/alerts", json=payload)

    response = await client.get("/api/v1/alerts", params={"skip": 1, "limit": 1})

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1


@pytest.mark.asyncio
async def test_list_alerts_includes_latest_reading_from_cache(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    await client.post("/api/v1/alerts", json=ALERT_PAYLOAD)
    await alert_repo.upsert_cache(
        db_session,
        lat=ALERT_PAYLOAD["latitude"],
        lon=ALERT_PAYLOAD["longitude"],
        payload_json={"pollutants": {"pm2_5": 12.5, "pm10": 20.0}},
        aqi=2,
        fetched_at=datetime(2026, 3, 21, 12, 0, tzinfo=UTC),
    )
    await db_session.flush()

    response = await client.get("/api/v1/alerts")

    assert response.status_code == 200
    alert = response.json()[0]
    assert alert["latest_reading"] is not None
    assert alert["latest_reading"]["pollutants"]["pm2_5"] == 12.5
    assert alert["latest_reading"]["aqi"] == 2
    assert alert["criticality"] == "within_limit"


@pytest.mark.asyncio
async def test_list_alerts_filters_by_criticality(
    client: AsyncClient,
    db_session: AsyncSession,
) -> None:
    within_payload = {**ALERT_PAYLOAD, "local_name": "Dentro do limite"}
    above_payload = {
        **ALERT_PAYLOAD,
        "local_name": "Acima do limite",
        "latitude": -22.9068,
        "longitude": -43.1729,
        "concentration_limit": 10.0,
    }
    await client.post("/api/v1/alerts", json=within_payload)
    await client.post("/api/v1/alerts", json=above_payload)

    await alert_repo.upsert_cache(
        db_session,
        lat=within_payload["latitude"],
        lon=within_payload["longitude"],
        payload_json={"pollutants": {"pm2_5": 8.0}},
        aqi=1,
        fetched_at=datetime(2026, 3, 21, 12, 0, tzinfo=UTC),
    )
    await alert_repo.upsert_cache(
        db_session,
        lat=above_payload["latitude"],
        lon=above_payload["longitude"],
        payload_json={"pollutants": {"pm2_5": 18.0}},
        aqi=3,
        fetched_at=datetime(2026, 3, 21, 12, 0, tzinfo=UTC),
    )
    await db_session.flush()

    response = await client.get(
        "/api/v1/alerts",
        params={"criticality": "above_limit"},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["local_name"] == "Acima do limite"
    assert body[0]["criticality"] == "above_limit"
