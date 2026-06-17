from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models import User, UserRole


def seed_admin_user(db: Session, settings: Settings) -> User | None:
    if not settings.admin_email or not settings.admin_password:
        return None

    email = settings.admin_email.lower()
    user = db.query(User).filter(func.lower(User.email) == email).first()
    if user:
        user.role = UserRole.admin
        user.full_name = user.full_name or settings.admin_full_name
        user.hashed_password = hash_password(settings.admin_password)
        if not user.is_active:
            user.is_active = True
        db.commit()
        db.refresh(user)
        return user

    admin = User(
        email=email,
        full_name=settings.admin_full_name,
        hashed_password=hash_password(settings.admin_password),
        role=UserRole.admin,
        is_active=True,
    )
    db.add(admin)
    db.commit()
    db.refresh(admin)
    return admin
