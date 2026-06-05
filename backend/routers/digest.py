from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user
from core.logging import get_logger
from database import get_db
from models import User
from schemas import DigestPreference, DigestPreferenceUpdate
from services.digest_service import DigestService, get_digest_service
from services.email_service import EmailService, get_email_service

router = APIRouter(dependencies=[Depends(get_current_user)])
logger = get_logger(__name__)


@router.get("/api/digest/preference", response_model=DigestPreference)
def get_preference(
    current_user: User = Depends(get_current_user),
    email_svc: EmailService = Depends(get_email_service),
):
    return DigestPreference(enabled=current_user.digest_opt_in, email_configured=email_svc.enabled)


@router.put("/api/digest/preference", response_model=DigestPreference)
def set_preference(
    payload: DigestPreferenceUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    email_svc: EmailService = Depends(get_email_service),
):
    current_user.digest_opt_in = payload.enabled
    db.commit()
    logger.info("Digest opt-in set to %s for user %d", payload.enabled, current_user.id)
    return DigestPreference(enabled=current_user.digest_opt_in, email_configured=email_svc.enabled)


@router.post("/api/digest/test")
def send_test_digest(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    digest_svc: DigestService = Depends(get_digest_service),
    email_svc: EmailService = Depends(get_email_service),
):
    if not email_svc.enabled:
        raise HTTPException(status_code=503, detail="Email is not configured on the server.")
    if not digest_svc.send_for_user(db, current_user):
        raise HTTPException(status_code=502, detail="Failed to send the digest email — check server email settings.")
    return {"sent": True}
