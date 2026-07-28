from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models import HelpCenterArticle, User, UserRole

SAFETY_SCOPE_ARTICLE_TITLE = "How Dental AI's safety checks work (and their limits)"


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


def seed_safety_scope_help_article(db: Session) -> None:
    """Phase 8 (docs/PRODUCT_BENCHMARK.md finding: 'verified safety/self-check beyond
    regex... or an explicit, communicated scope limit'). Building a clinically-validated
    safety classifier is out of scope for a single hardening pass and would be
    irresponsible to fake - a hastily-built 'classifier' that hasn't actually been
    validated is worse than the current honest, pattern-based system, not better. The
    real gap this closes is that the scope and limits of what run_safety_check()
    actually does (app/agent/nodes/safety.py) were only ever documented in code
    comments - genuinely invisible to the people who most need to know them: patients
    relying on it, and the admins/clinicians accountable for it. This seeds that
    disclosure as a real, user-reachable Help Center article instead. Idempotent (checked
    by title) so it's safe to call on every startup, and an admin can edit or replace the
    seeded copy afterward - this only fills the slot if it's empty."""
    existing = db.query(HelpCenterArticle).filter(HelpCenterArticle.title == SAFETY_SCOPE_ARTICLE_TITLE).first()
    if existing:
        return

    content = (
        "Dental AI includes automated checks meant to catch clearly dangerous situations "
        "and flag answers that might not be well-supported by our reference material. "
        "It's important to understand exactly what these checks are - and are not.\n\n"
        "What they are:\n"
        "- A fixed list of red-flag phrases (for example, rapidly spreading facial "
        "swelling combined with difficulty breathing) triggers an immediate, pre-written "
        "message telling you to seek emergency care right away, without waiting for the "
        "AI to generate a response.\n"
        "- Questions involving specific medications, dosages, or prescriptions are "
        "automatically redirected toward consulting a licensed dentist rather than "
        "answered directly.\n"
        "- Every answer is checked for whether its claims are actually supported by the "
        "retrieved reference material; unsupported claims are trimmed or flagged.\n\n"
        "What they are not:\n"
        "- This is not a clinical diagnostic system and has not been validated as one. "
        "It cannot examine you, order tests, or make a diagnosis.\n"
        "- The red-flag detection is pattern-based (keyword and phrase matching), not a "
        "trained medical AI model. It will miss emergencies described in unfamiliar "
        "wording, and it is not a substitute for recognizing your own symptoms and "
        "seeking care when something feels seriously wrong.\n"
        "- These checks reduce risk; they do not eliminate it.\n\n"
        "When in doubt, always contact a licensed dentist or emergency services directly "
        "- especially for pain, swelling, bleeding, fever, trauma, medication questions, "
        "or anything you are unsure about. Dental AI is designed to support your "
        "understanding, not replace professional judgment."
    )

    db.add(
        HelpCenterArticle(
            title=SAFETY_SCOPE_ARTICLE_TITLE,
            content=content,
            category="safety",
            tags="safety,limitations,emergency",
            is_published=True,
            order_index=0,
        )
    )
    db.commit()
