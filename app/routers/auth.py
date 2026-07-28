from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import get_settings
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
from app.core.token_blocklist import bind_refresh_token_to_device, refresh_token_device_mismatch, revoke_access_token


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


def _create_refresh_token_with_expiry(db: Session, user: User, request: Request | None = None) -> str:
    settings = get_settings()
    refresh_token = create_refresh_token(user.id)
    expires_at = datetime.now(timezone.utc) + timedelta(days=settings.refresh_token_expire_days)
    token_hash = hash_token(refresh_token)
    db.add(RefreshToken(
        user_id=user.id,
        token_hash=token_hash,
        expires_at=expires_at,
    ))
    if request is not None:
        bind_refresh_token_to_device(
            token_hash,
            request.headers.get("user-agent", ""),
            ttl_seconds=settings.refresh_token_expire_days * 86400,
        )
    return refresh_token


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

    requesting_dentist = role == UserRole.dentist
    if requesting_dentist:
        # Phase 8 fix (docs/PRODUCT_BENCHMARK.md finding #1): this used to reject
        # dentist registration outright with no way for an admin to ever grant one -
        # the UI promised "admin verification required" but nothing behind it could
        # verify anyone. The account is created now (usable immediately as a patient
        # account) with a pending verification request instead of being turned away;
        # role only becomes UserRole.dentist once an admin approves it via
        # POST /admin/dentist-requests/{user_id}/approve.
        if not payload.license_number:
            raise HTTPException(status_code=422, detail="license_number is required when requesting a dentist account")
        role = UserRole.patient

    user = User(
        email=payload.email.lower(),
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        role=role,
    )
    if requesting_dentist:
        user.dentist_verification_status = "pending"
        user.dentist_license_number = payload.license_number
        user.dentist_clinic_name = payload.clinic_name
        user.dentist_verification_requested_at = datetime.now(timezone.utc)
    db.add(user)
    db.flush()

    access_token = create_access_token(user.id, {"role": user.role.value})
    refresh_token = _create_refresh_token_with_expiry(db, user, request)

    audit_detail = f"Role: {role.value}" + (" (dentist verification requested)" if requesting_dentist else "")
    _log_audit(db, user.id, "register", "user", request, audit_detail)
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
    refresh_token = _create_refresh_token_with_expiry(db, user, request)

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

    # Soft device-binding check (Phase 2, non-blocking - see
    # token_blocklist.refresh_token_device_mismatch docstring for why this doesn't reject
    # the request outright).
    if refresh_token_device_mismatch(token_hash, request.headers.get("user-agent", "")):
        _log_audit(db, user.id, "token_refresh_device_mismatch", "user", request)

    stored_token.revoked = True
    stored_token.revoked_at = datetime.now(timezone.utc)

    new_access = create_access_token(user.id, {"role": user.role.value})
    new_refresh = _create_refresh_token_with_expiry(db, user, request)

    _log_audit(db, user.id, "token_refresh", "user", request)
    db.commit()
    db.refresh(user)
    return Token(
        access_token=new_access,
        refresh_token=new_refresh,
        user=UserRead.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    payload: TokenRefreshRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    token_hash = hash_token(payload.refresh_token)
    stored_token = db.query(RefreshToken).filter(
        RefreshToken.token_hash == token_hash,
        RefreshToken.user_id == current_user.id,
    ).first()
    if stored_token:
        stored_token.revoked = True
        stored_token.revoked_at = datetime.now(timezone.utc)
        db.commit()

    # Revoke the access token used for THIS request too - previously logout only revoked
    # the refresh token, leaving the (up to access_token_expire_minutes-old) access token
    # fully valid until its natural expiry even after the user explicitly logged out.
    access_payload = getattr(request.state, "access_token_payload", None)
    if access_payload:
        settings = get_settings()
        remaining_seconds = max(1, int(access_payload.get("exp", 0) - datetime.now(timezone.utc).timestamp()))
        revoke_access_token(access_payload.get("jti"), ttl_seconds=min(remaining_seconds, settings.access_token_expire_minutes * 60))


@router.get("/me", response_model=UserRead)
def me(current_user: User = Depends(get_current_user)) -> UserRead:
    return UserRead.model_validate(current_user)
