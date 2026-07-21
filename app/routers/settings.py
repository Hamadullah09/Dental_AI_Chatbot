from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user, require_admin
from app.models import HelpCenterArticle, SupportTicket, User, UserRole, UserSettings
from app.schemas import (
    ContactSupportCreate,
    ContactSupportRead,
    FeedbackCreateExtended,
    HelpArticleCreate,
    HelpArticleRead,
    HelpArticleUpdate,
    HelpCategoryRead,
    UserPreferencesRead,
    UserPreferencesUpdate,
    UserSettingsRead,
    UserSettingsUpdate,
)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=UserSettingsRead)
def get_settings(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSettingsRead:
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)
        db.commit()
        db.refresh(settings)
    return UserSettingsRead.model_validate(settings)


@router.patch("", response_model=UserSettingsRead)
def update_settings(
    payload: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserSettingsRead:
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(settings, key, value)

    settings.updated_at = datetime.now()
    db.commit()
    db.refresh(settings)

    return UserSettingsRead.model_validate(settings)


@router.post("/download-data")
def download_personal_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    data = {
        "user": {
            "id": current_user.id,
            "email": current_user.email,
            "full_name": current_user.full_name,
            "role": current_user.role.value,
            "created_at": current_user.created_at.isoformat() if current_user.created_at else None,
        },
        "settings": {},
        "appointments": [],
        "prescriptions": [],
        "dental_records": [],
        "chat_sessions": [],
    }

    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if settings:
        data["settings"] = UserSettingsRead.model_validate(settings).model_dump()

    from app.models import Appointment, Prescription, DentalRecord, ChatSession
    appointments = db.query(Appointment).filter(Appointment.patient_id == current_user.id).all()
    data["appointments"] = [a.__dict__ for a in appointments]

    prescriptions = db.query(Prescription).filter(Prescription.patient_id == current_user.id).all()
    data["prescriptions"] = [p.__dict__ for p in prescriptions]

    records = db.query(DentalRecord).filter(DentalRecord.patient_id == current_user.id).all()
    data["dental_records"] = [r.__dict__ for r in records]

    sessions = db.query(ChatSession).filter(ChatSession.user_id == current_user.id).all()
    data["chat_sessions"] = [s.__dict__ for s in sessions]

    return data


@router.post("/delete-account")
def delete_account(
    password: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.core.security import verify_password

    if not verify_password(password, current_user.hashed_password):
        raise HTTPException(status_code=400, detail="Invalid password")

    current_user.is_active = False
    db.commit()

    return {"message": "Account deactivated successfully"}


@router.post("/two-factor/enable")
def enable_two_factor(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    import pyotp

    secret = pyotp.random_base32()
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.add(settings)

    settings.two_factor_secret = secret
    settings.two_factor_enabled = True
    settings.updated_at = datetime.now()
    db.commit()

    uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.email,
        issuer_name="Dental AI Chatbot",
    )

    return {"secret": secret, "uri": uri}


@router.post("/two-factor/disable")
def disable_two_factor(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    settings = db.query(UserSettings).filter(UserSettings.user_id == current_user.id).first()
    if settings:
        settings.two_factor_secret = None
        settings.two_factor_enabled = False
        settings.updated_at = datetime.now()
        db.commit()

    return {"message": "Two-factor authentication disabled"}


@router.get("/sessions")
def get_active_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[dict]:
    from app.models import RefreshToken
    tokens = db.query(RefreshToken).filter(
        RefreshToken.user_id == current_user.id,
        RefreshToken.revoked.is_(False),
    ).all()

    return [
        {
            "id": t.id,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "expires_at": t.expires_at.isoformat() if t.expires_at else None,
        }
        for t in tokens
    ]


@router.delete("/sessions/{session_id}")
def revoke_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.models import RefreshToken
    token = db.query(RefreshToken).filter(
        RefreshToken.id == session_id,
        RefreshToken.user_id == current_user.id,
    ).first()

    if not token:
        raise HTTPException(status_code=404, detail="Session not found")

    token.revoked = True
    token.revoked_at = datetime.now()
    db.commit()

    return {"message": "Session revoked"}


# Help Center Routes
help_router = APIRouter(prefix="/help", tags=["help"])


@help_router.get("/categories", response_model=list[HelpCategoryRead])
def get_help_categories(db: Session = Depends(get_db)) -> list[HelpCategoryRead]:
    categories = db.query(
        HelpCenterArticle.category,
        func.count(HelpCenterArticle.id).label("count"),
    ).filter(HelpCenterArticle.is_published.is_(True)).group_by(
        HelpCenterArticle.category
    ).all()

    return [HelpCategoryRead(category=c.category, count=c.count) for c in categories]


@help_router.get("/articles", response_model=list[HelpArticleRead])
def list_help_articles(
    category: str | None = Query(None),
    search: str | None = Query(None),
    db: Session = Depends(get_db),
) -> list[HelpArticleRead]:
    query = db.query(HelpCenterArticle).filter(HelpCenterArticle.is_published.is_(True))

    if category:
        query = query.filter(HelpCenterArticle.category == category)
    if search:
        query = query.filter(HelpCenterArticle.title.ilike(f"%{search}%"))

    articles = query.order_by(HelpCenterArticle.order_index, HelpCenterArticle.title).all()
    return [HelpArticleRead.model_validate(a) for a in articles]


@help_router.get("/articles/{article_id}", response_model=HelpArticleRead)
def get_help_article(article_id: str, db: Session = Depends(get_db)) -> HelpArticleRead:
    article = db.get(HelpCenterArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    if not article.is_published:
        raise HTTPException(status_code=404, detail="Article not found")
    return HelpArticleRead.model_validate(article)


@help_router.post("/contact", response_model=ContactSupportRead, status_code=status.HTTP_201_CREATED)
def contact_support(
    payload: ContactSupportCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ContactSupportRead:
    ticket = SupportTicket(
        user_id=current_user.id,
        subject=payload.subject,
        message=payload.message,
        category=payload.category,
        status="open",
        priority="normal",
    )
    db.add(ticket)
    db.commit()
    db.refresh(ticket)

    return ContactSupportRead.model_validate(ticket)


@help_router.get("/my-tickets", response_model=list[ContactSupportRead])
def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ContactSupportRead]:
    tickets = db.query(SupportTicket).filter(SupportTicket.user_id == current_user.id).order_by(
        SupportTicket.created_at.desc()
    ).all()
    return [ContactSupportRead.model_validate(t) for t in tickets]


@help_router.post("/feedback")
def submit_feedback(
    payload: FeedbackCreateExtended,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    from app.models import AuditLog
    log = AuditLog(
        user_id=current_user.id,
        action="feedback",
        resource_type="feedback",
        details=f"Type: {payload.type}, Rating: {payload.rating}, Message: {payload.message[:200]}",
    )
    db.add(log)
    db.commit()

    return {"message": "Feedback submitted successfully"}


# Admin Help Center Management
admin_help_router = APIRouter(prefix="/admin/help", tags=["admin-help"])


@admin_help_router.post("/articles", response_model=HelpArticleRead, status_code=status.HTTP_201_CREATED)
def create_help_article(
    payload: HelpArticleCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HelpArticleRead:
    article = HelpCenterArticle(
        title=payload.title,
        content=payload.content,
        category=payload.category,
        tags=",".join(payload.tags) if payload.tags else None,
        is_published=payload.is_published,
        order_index=payload.order,
    )
    db.add(article)
    db.commit()
    db.refresh(article)
    return HelpArticleRead.model_validate(article)


@admin_help_router.patch("/articles/{article_id}", response_model=HelpArticleRead)
def update_help_article(
    article_id: str,
    payload: HelpArticleUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HelpArticleRead:
    article = db.get(HelpCenterArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "tags" in update_data:
        update_data["tags"] = ",".join(update_data["tags"]) if update_data["tags"] else None
    if "order" in update_data:
        update_data["order_index"] = update_data.pop("order")

    for key, value in update_data.items():
        setattr(article, key, value)

    article.updated_at = datetime.now()
    db.commit()
    db.refresh(article)

    return HelpArticleRead.model_validate(article)


@admin_help_router.delete("/articles/{article_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_help_article(
    article_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    article = db.get(HelpCenterArticle, article_id)
    if not article:
        raise HTTPException(status_code=404, detail="Article not found")
    db.delete(article)
    db.commit()


@admin_help_router.get("/tickets", response_model=list[ContactSupportRead])
def list_support_tickets(
    status: str | None = Query(None),
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ContactSupportRead]:
    query = db.query(SupportTicket)
    if status:
        query = query.filter(SupportTicket.status == status)
    tickets = query.order_by(SupportTicket.created_at.desc()).all()
    return [ContactSupportRead.model_validate(t) for t in tickets]


@admin_help_router.patch("/tickets/{ticket_id}")
def update_ticket(
    ticket_id: str,
    response: str,
    status: str = "closed",
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ContactSupportRead:
    ticket = db.get(SupportTicket, ticket_id)
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    ticket.response = response
    ticket.status = status
    ticket.responded_at = datetime.now()
    ticket.assigned_to = current_user.id
    ticket.updated_at = datetime.now()
    db.commit()
    db.refresh(ticket)

    return ContactSupportRead.model_validate(ticket)


@router.get("/preferences", response_model=UserPreferencesRead)
def get_user_preferences(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesRead:
    from app.services.memory import MemoryService
    svc = MemoryService()
    context = svc.get_memory_context(current_user.id, db)
    prefs = context.get("preferences", {})
    return UserPreferencesRead(
        preferred_language=prefs.get("preferred_language", "en"),
        simplify_for_patient=prefs.get("simplify_for_patient", False),
        preferred_specialty=prefs.get("preferred_specialty", ""),
        frequently_asked_topics=context.get("recent_topics", []),
        recent_sessions=context.get("recent_sessions", []),
    )


@router.patch("/preferences", response_model=UserPreferencesRead)
def update_user_preferences(
    payload: UserPreferencesUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserPreferencesRead:
    from app.services.memory import MemoryService
    svc = MemoryService()
    svc.update_memory(
        current_user.id,
        preferred_language=payload.preferred_language,
        simplify_for_patient=payload.simplify_for_patient,
        preferred_specialty=payload.preferred_specialty,
    )
    context = svc.get_memory_context(current_user.id, db)
    prefs = context.get("preferences", {})
    return UserPreferencesRead(
        preferred_language=prefs.get("preferred_language", "en"),
        simplify_for_patient=prefs.get("simplify_for_patient", False),
        preferred_specialty=prefs.get("preferred_specialty", ""),
        frequently_asked_topics=context.get("recent_topics", []),
        recent_sessions=context.get("recent_sessions", []),
    )