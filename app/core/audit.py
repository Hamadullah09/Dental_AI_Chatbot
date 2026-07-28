from __future__ import annotations

from fastapi import Request
from sqlalchemy.orm import Session

from app.models import AuditLog


def log_access(
    db: Session,
    *,
    user_id: str | None,
    action: str,
    resource_type: str,
    resource_id: str | None = None,
    request: Request | None = None,
    details: str | None = None,
    commit: bool = True,
) -> None:
    """Field-level access audit logging for PHI-bearing resources (Phase 2). Shared by the
    clinical routers (dental_records, prescriptions) which previously logged nothing at
    all - every read and write of a patient's diagnoses, medications, or prescriptions was
    invisible to any later audit or incident investigation."""
    log = AuditLog(
        user_id=user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
        ip_address=request.client.host if request and request.client else None,
        user_agent=request.headers.get("user-agent", "")[:500] if request else None,
    )
    db.add(log)
    if commit:
        db.commit()
