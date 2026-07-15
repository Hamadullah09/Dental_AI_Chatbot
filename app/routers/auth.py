from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.deps import get_current_user
from app.models import AuditLog, RefreshToken, User, UserRole
from app.schemas import LoginRequest, Token, TokenRefreshRequest, UserCreate, UserRead
from app.core.redis import RateLimiter


router = APIRouter(prefix="/auth", tags=["auth"])
rate_limiter = RateLimiter(prefix="ratelimit:auth")


def _log_audit(db: Session, user_id: str | None, action: str, resource_type: str, request: Request | None = None, details: str | None = None) -> None:
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        details=details,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] if request else None,
    )
    db.add(log)


@router.post("/register", response_model=Token, status_code=status.HTTP_201_CREATED)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)) -> Token:
    if rate_limiter.is_rate_limited(f"register:{request.client.host}", 5, 300):
        raise HTTPException(status_code=429, detail="Too many registration attempts. Please try again later.")

    existing = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email is already registered")

    role = payload.role
    if role == UserRole.admin:
        raise HTTPException(status_code=403, detail="Admin accounts are created by system configuration only")
    if role == UserRole.dentist:
        raise HTTPException(
            status_code=403,
            detail="Dentist accounts require credential verification by an admin before clinical access is enabled.",
        )

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=role,
    )
    db.add(user)
    db.flush()

    access_token = create_access_token(user.id, {"role": user.role.value})
    refresh_token = create_refresh_token(user.id)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc).replace(
            hour=23, minute=59, second=59
        ),
    ))

    _log_audit(db, user.id, "register", "user", request, f"Role: {role.value}")
    db.commit()
    db.refresh(user)
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserRead.model_validate(user),
    )


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    if rate_limiter.is_rate_limited(f"login:{request.client.host}", 10, 60):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again later.")

    user = db.query(User).filter(func.lower(User.email) == payload.email.lower()).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    access_token = create_access_token(user.id, {"role": user.role.value})
    refresh_token = create_refresh_token(user.id)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(refresh_token),
        expires_at=datetime.now(timezone.utc).replace(
            hour=23, minute=59, second=59
        ),
    ))

    _log_audit(db, user.id, "login", "user", request)
    db.commit()
    db.refresh(user)
    return Token(
        access_token=access_token,
        refresh_token=refresh_token,
        user=UserRead.model_validate(user),
    )


@router.post("/refresh", response_model=Token)
def refresh_token(payload: TokenRefreshRequest, request: Request, db: Session = Depends(get_db)) -> Token:
    if rate_limiter.is_rate_limited(f"refresh:{request.client.host}", 20, 60):
        raise HTTPException(status_code=429, detail="Too many refresh attempts.")

    try:
        token_data = decode_refresh_token(payload.refresh_token)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    user_id = token_data.get("sub")
    token_hash = hash_token(payload.refresh_token)
    stored_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == user_id,
    ).first()

    if not stored_token or stored_token.revoked:
        raise HTTPException(status_code=401, detail="Refresh token has been revoked")

    if stored_token.expires_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Refresh token has expired")

    user = db.get(User, user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    stored_token.revoked = True
    stored_token.revoked_at = datetime.now(timezone.utc)

    new_access = create_access_token(user.id, {"role": user.role.value})
    new_refresh = create_refresh_token(user.id)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=hash_token(new_refresh),
        expires_at=datetime.now(timezone.utc).replace(
            hour=23, minute=59, second=59
        ),
    ))

    _log_audit(db, user.id, "token_refresh", "user", request)
    db.commit()
    db.refresh(user)
    return Token(
        access_token=new_access,
        refresh_token=new_refresh,
        user=UserRead.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(payload: TokenRefreshRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    token_hash = hash_token(payload.refresh_token)
    stored_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == current_user.id,
    ).first()
    if stored_token:
        stored_token.revoked = True
        stored_token.revoked_at = datetime.now(timezone.utc)
        db.commit()


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
