from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from core.logging import get_logger
from database import get_db
from dependencies import get_alert_service, get_push_repo
from models import User
from repositories.push_repository import PushSubscriptionRepository
from schemas import (
    AlertCreate,
    AlertResponse,
    AlertUpdate,
    PushSubscriptionCreate,
    VapidKeyResponse,
)
from services.alert_service import AlertService
from services.push_service import PushService, get_push_service

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = get_logger(__name__)


# ---- Price alerts ----------------------------------------------------------

@router.get("/api/alerts", response_model=list[AlertResponse])
def list_alerts(alert_svc: AlertService = Depends(get_alert_service)):
    return alert_svc.list()


@router.post("/api/alerts", response_model=AlertResponse, status_code=201)
def create_alert(payload: AlertCreate, alert_svc: AlertService = Depends(get_alert_service)):
    return alert_svc.create(payload)


@router.put("/api/alerts/{alert_id}", response_model=AlertResponse)
def update_alert(
    alert_id: int,
    payload: AlertUpdate,
    alert_svc: AlertService = Depends(get_alert_service),
):
    result = alert_svc.set_active(alert_id, payload.active)
    if result is None:
        raise HTTPException(status_code=404, detail="Alert not found")
    return result


@router.delete("/api/alerts/{alert_id}", status_code=204)
def delete_alert(alert_id: int, alert_svc: AlertService = Depends(get_alert_service)):
    if not alert_svc.delete(alert_id):
        raise HTTPException(status_code=404, detail="Alert not found")


# ---- Push notifications ----------------------------------------------------

class _Unsubscribe(BaseModel):
    endpoint: str


@router.get("/api/push/vapid-public-key", response_model=VapidKeyResponse)
def vapid_public_key(push_svc: PushService = Depends(get_push_service)):
    return VapidKeyResponse(public_key=push_svc.public_key, enabled=push_svc.enabled)


@router.post("/api/push/subscribe", status_code=201)
def subscribe_push(
    payload: PushSubscriptionCreate,
    push_repo: PushSubscriptionRepository = Depends(get_push_repo),
):
    push_repo.upsert(payload.endpoint, payload.keys.p256dh, payload.keys.auth)
    return {"status": "subscribed"}


@router.post("/api/push/unsubscribe", status_code=204)
def unsubscribe_push(
    payload: _Unsubscribe,
    push_repo: PushSubscriptionRepository = Depends(get_push_repo),
):
    push_repo.delete_by_endpoint(payload.endpoint)


@router.post("/api/push/test")
def test_push(
    current_user: User = Depends(get_current_user),
    push_svc: PushService = Depends(get_push_service),
    db: Session = Depends(get_db),
):
    if not push_svc.enabled:
        raise HTTPException(status_code=503, detail="Push notifications are not configured on the server.")
    sent = push_svc.send_to_user(
        db, current_user.id,
        title="🔔 Test notification",
        body="Push notifications are working. You'll be alerted when your price targets hit.",
        url="/alerts",
    )
    if sent == 0:
        raise HTTPException(status_code=404, detail="No active subscription for this device. Enable notifications first.")
    return {"sent": sent}
