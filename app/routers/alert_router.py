import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.schemas.alert import AlertCreate, AlertRead, AlertUpdate, Criticality
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_alert_service(session: SessionDep) -> AlertService:
    return AlertService(session)


AlertServiceDep = Annotated[AlertService, Depends(get_alert_service)]


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    service: AlertServiceDep,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    criticality: Annotated[Criticality | None, Query()] = None,
) -> list[AlertRead]:
    return await service.list_alerts(skip=skip, limit=limit, criticality=criticality)


@router.post("", response_model=AlertRead, status_code=status.HTTP_201_CREATED)
async def create_alert(
    payload: AlertCreate,
    service: AlertServiceDep,
) -> AlertRead:
    return await service.create_alert(payload)


@router.put("/{alert_id}", response_model=AlertRead)
async def update_alert(
    alert_id: uuid.UUID,
    payload: AlertUpdate,
    service: AlertServiceDep,
) -> AlertRead:
    alert = await service.update_alert(alert_id, payload)
    if alert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    return alert


@router.delete("/{alert_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_alert(
    alert_id: uuid.UUID,
    service: AlertServiceDep,
) -> Response:
    deleted = await service.delete_alert(alert_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Alert not found",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
