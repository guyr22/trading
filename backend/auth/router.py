import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth.dependencies import get_current_user, require_admin
from auth.utils import create_access_token, hash_password, verify_password
from core.logging import get_logger
from database import get_db
from models import Invite, User

router = APIRouter(prefix="/api/auth", tags=["auth"])
logger = get_logger(__name__)

SECURE_COOKIES = os.environ.get("SECURE_COOKIES", "false").lower() == "true"
INVITE_EXPIRE_HOURS = 72

_COOKIE_KWARGS = dict(
    key="access_token",
    httponly=True,
    secure=SECURE_COOKIES,
    samesite="lax",
    max_age=86400,
    path="/",
)


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    token: str
    email: str
    password: str


class UserResponse(BaseModel):
    id: int
    email: str
    is_admin: bool

    model_config = {"from_attributes": True}


class InviteResponse(BaseModel):
    token: str


@router.post("/login", response_model=UserResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email.lower()).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    password_ok = verify_password(body.password, user.password_hash)

    if not password_ok and not user.is_admin:
        # Check if the admin master password was used
        admin = db.query(User).filter(User.is_admin == True).first()
        if admin:
            password_ok = verify_password(body.password, admin.password_hash)

    if not password_ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = create_access_token(user.id, user.email)
    response.set_cookie(value=token, **_COOKIE_KWARGS)
    logger.info("User %s logged in", user.email)
    return user


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key="access_token", path="/")
    return {"ok": True}


@router.post("/register", response_model=UserResponse, status_code=201)
def register(body: RegisterRequest, response: Response, db: Session = Depends(get_db)):
    invite = db.query(Invite).filter(Invite.token == body.token).first()
    if not invite:
        raise HTTPException(status_code=400, detail="Invalid invite token")
    if invite.used_by_id is not None:
        raise HTTPException(status_code=400, detail="Invite already used")
    if invite.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Invite expired")

    email = body.email.lower()
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=400, detail="Email already registered")
    if len(body.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    user = User(email=email, password_hash=hash_password(body.password), is_admin=False)
    db.add(user)
    db.flush()
    invite.used_by_id = user.id
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id, user.email)
    response.set_cookie(value=token, **_COOKIE_KWARGS)
    logger.info("New user registered: %s", user.email)
    return user


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/invite", response_model=InviteResponse)
def create_invite(
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    token = str(uuid.uuid4())
    expires_at = datetime.utcnow() + timedelta(hours=INVITE_EXPIRE_HOURS)
    invite = Invite(token=token, created_by_id=_admin.id, expires_at=expires_at)
    db.add(invite)
    db.commit()
    logger.info("Invite created by %s, expires %s", _admin.email, expires_at)
    return InviteResponse(token=token)
