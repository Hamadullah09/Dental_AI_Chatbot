from datetime import datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user, require_admin
from app.models import Appointment, AppointmentStatus, Dentist, User, UserRole
from app.schemas import (
    AppointmentCreate,
    AppointmentRead,
    AppointmentSearchParams,
    AppointmentSearchResult,
    AppointmentStatusUpdate,
    AppointmentUpdate,
)

router = APIRouter(prefix="/appointments", tags=["appointments"])


@router.get("", response_model=AppointmentSearchResult)
def search_appointments(
    params: AppointmentSearchParams = Depends(),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentSearchResult:
    query = db.query(Appointment)

    if current_user.role == UserRole.patient:
        query = query.filter(Appointment.patient_id == current_user.id)
    elif current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if dentist:
            query = query.filter(Appointment.dentist_id == dentist.id)
        else:
            return AppointmentSearchResult(appointments=[], total=0, page=params.page, limit=params.limit, total_pages=0)

    if params.status:
        query = query.filter(Appointment.status == params.status)

    if params.dentist_id:
        query = query.filter(Appointment.dentist_id == params.dentist_id)

    if params.patient_id and current_user.role == UserRole.admin:
        query = query.filter(Appointment.patient_id == params.patient_id)

    if params.date_from:
        query = query.filter(Appointment.appointment_date >= params.date_from)
    if params.date_to:
        query = query.filter(Appointment.appointment_date <= params.date_to)

    if params.query:
        search = f"%{params.query}%"
        query = query.join(Dentist).filter(
            or_(
                Dentist.full_name.ilike(search),
                Dentist.clinic_name.ilike(search),
                Appointment.chief_complaint.ilike(search),
            )
        )

    total = query.count()
    total_pages = (total + params.limit - 1) // params.limit
    offset = (params.page - 1) * params.limit

    appointments = query.order_by(Appointment.appointment_date.desc()).offset(offset).limit(params.limit).all()

    return AppointmentSearchResult(
        appointments=[AppointmentRead.from_orm_model(a) for a in appointments],
        total=total,
        page=params.page,
        limit=params.limit,
        total_pages=total_pages,
    )


@router.get("/upcoming")
def get_upcoming_appointments(
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AppointmentRead]:
    now = datetime.now()
    query = db.query(Appointment).filter(
        Appointment.appointment_date >= now,
        Appointment.status.in_([AppointmentStatus.pending, AppointmentStatus.confirmed]),
    )

    if current_user.role == UserRole.patient:
        query = query.filter(Appointment.patient_id == current_user.id)
    elif current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if dentist:
            query = query.filter(Appointment.dentist_id == dentist.id)

    appointments = query.order_by(Appointment.appointment_date).limit(limit).all()
    return [AppointmentRead.from_orm_model(a) for a in appointments]


@router.get("/{appointment_id}", response_model=AppointmentRead)
def get_appointment(
    appointment_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentRead:
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if current_user.role == UserRole.patient and appointment.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to view this appointment")
    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or appointment.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized to view this appointment")

    return AppointmentRead.from_orm_model(appointment)


@router.post("", response_model=AppointmentRead, status_code=status.HTTP_201_CREATED)
def create_appointment(
    payload: AppointmentCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentRead:
    if current_user.role not in [UserRole.patient, UserRole.admin]:
        raise HTTPException(status_code=403, detail="Only patients can book appointments")

    dentist = db.get(Dentist, payload.dentist_id)
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist not found")
    if not dentist.is_active:
        raise HTTPException(status_code=400, detail="Dentist is not accepting appointments")

    appointment_date = payload.appointment_date
    duration = payload.duration_minutes or 30
    appointment_end = appointment_date + timedelta(minutes=duration)

    conflict = db.query(Appointment).filter(
        Appointment.dentist_id == payload.dentist_id,
        Appointment.appointment_date < appointment_end,
        Appointment.appointment_end > appointment_date,
        Appointment.status.in_([AppointmentStatus.pending, AppointmentStatus.confirmed]),
    ).first()

    if conflict:
        raise HTTPException(status_code=409, detail="Time slot is already booked")

    appointment = Appointment(
        patient_id=current_user.id if current_user.role == UserRole.patient else payload.patient_id,
        dentist_id=payload.dentist_id,
        appointment_date=appointment_date,
        appointment_end=appointment_end,
        chief_complaint=payload.reason,
        notes=payload.notes,
        status=AppointmentStatus.pending,
    )
    db.add(appointment)
    db.commit()
    db.refresh(appointment)

    return AppointmentRead.from_orm_model(appointment)


@router.patch("/{appointment_id}", response_model=AppointmentRead)
def update_appointment(
    appointment_id: str,
    payload: AppointmentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentRead:
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if current_user.role == UserRole.patient and appointment.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this appointment")
    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or appointment.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized to update this appointment")

    update_data = payload.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(appointment, key, value)

    appointment.updated_at = datetime.now()
    db.commit()
    db.refresh(appointment)

    return AppointmentRead.from_orm_model(appointment)


@router.patch("/{appointment_id}/status", response_model=AppointmentRead)
def update_appointment_status(
    appointment_id: str,
    payload: AppointmentStatusUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentRead:
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    allowed_transitions = {
        AppointmentStatus.pending: [AppointmentStatus.confirmed, AppointmentStatus.cancelled, AppointmentStatus.rejected],
        AppointmentStatus.confirmed: [AppointmentStatus.completed, AppointmentStatus.cancelled, AppointmentStatus.rescheduled],
        AppointmentStatus.rescheduled: [AppointmentStatus.completed, AppointmentStatus.cancelled],
    }

    current_status = appointment.status
    new_status = payload.status

    if current_user.role == UserRole.patient:
        if appointment.patient_id != current_user.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        if current_status not in [AppointmentStatus.pending, AppointmentStatus.confirmed]:
            raise HTTPException(status_code=400, detail="Cannot cancel this appointment")
        if new_status != AppointmentStatus.cancelled:
            raise HTTPException(status_code=403, detail="Patients can only cancel appointments")

    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or appointment.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")
        if new_status not in allowed_transitions.get(current_status, []):
            raise HTTPException(status_code=400, detail=f"Cannot transition from {current_status} to {new_status}")

    appointment.status = new_status
    if new_status == AppointmentStatus.cancelled:
        appointment.cancellation_reason = payload.reason
        appointment.cancelled_by = current_user.id
        appointment.cancelled_at = datetime.now()
    elif new_status == AppointmentStatus.rescheduled:
        appointment.rescheduled_from_id = appointment_id

    appointment.updated_at = datetime.now()
    db.commit()
    db.refresh(appointment)

    return AppointmentRead.from_orm_model(appointment)


@router.post("/{appointment_id}/reschedule", response_model=AppointmentRead)
def reschedule_appointment(
    appointment_id: str,
    new_date: datetime,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AppointmentRead:
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")

    if current_user.role == UserRole.patient and appointment.patient_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized")
    if current_user.role == UserRole.dentist:
        dentist = db.query(Dentist).filter(Dentist.user_id == current_user.id).first()
        if not dentist or appointment.dentist_id != dentist.id:
            raise HTTPException(status_code=403, detail="Not authorized")

    new_end = new_date + timedelta(minutes=30)
    conflict = db.query(Appointment).filter(
        Appointment.dentist_id == appointment.dentist_id,
        Appointment.appointment_date < new_end,
        Appointment.appointment_end > new_date,
        Appointment.status.in_([AppointmentStatus.pending, AppointmentStatus.confirmed]),
        Appointment.id != appointment_id,
    ).first()

    if conflict:
        raise HTTPException(status_code=409, detail="Time slot is already booked")

    old_appointment = Appointment(
        patient_id=appointment.patient_id,
        dentist_id=appointment.dentist_id,
        appointment_date=appointment.appointment_date,
        appointment_end=appointment.appointment_end,
        status=AppointmentStatus.rescheduled,
        chief_complaint=appointment.chief_complaint,
        notes=appointment.notes,
        rescheduled_from_id=appointment.id,
    )
    db.add(old_appointment)

    appointment.appointment_date = new_date
    appointment.appointment_end = new_end
    appointment.status = AppointmentStatus.rescheduled
    appointment.updated_at = datetime.now()

    db.commit()
    db.refresh(appointment)

    return AppointmentRead.from_orm_model(appointment)


@router.delete("/{appointment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_appointment(
    appointment_id: str,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    appointment = db.get(Appointment, appointment_id)
    if not appointment:
        raise HTTPException(status_code=404, detail="Appointment not found")
    db.delete(appointment)
    db.commit()