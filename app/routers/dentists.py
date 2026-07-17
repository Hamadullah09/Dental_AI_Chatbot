"""Dentist API router with scraper integration."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.deps import get_current_user, require_admin
from app.models import Appointment, Dentist, DentistAvailability, DentistSpecialization, User, UserRole
from app.repositories.dentist_repo import DentistRepository
from app.schemas import (
    AppointmentStatus,
    DentistCreate,
    DentistRead,
    DentistSearchParams,
    DentistSearchResult,
    DentistUpdate,
    TimeSlot,
    DentistFullRead,
    DentistSearchParamsV2,
    DentistSearchResultV2,
    DentistSpecializationStat,
    ExportResponse,
    ReindexRequest,
    SyncRequest,
    SyncResultResponse,
)
from app.services.scraper.sync_service import DentistSyncService, SyncResult

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/dentists", tags=["dentists"])
settings = get_settings()


def _map_specialization(spec: str) -> DentistSpecialization:
    mapping = {
        "general": DentistSpecialization.general_dentistry,
        "orthodontics": DentistSpecialization.orthodontics,
        "periodontics": DentistSpecialization.periodontics,
        "endodontics": DentistSpecialization.endodontics,
        "prosthodontics": DentistSpecialization.prosthodontics,
        "oral surgery": DentistSpecialization.oral_surgery,
        "pediatric": DentistSpecialization.pediatric_dentistry,
        "cosmetic": DentistSpecialization.cosmetic_dentistry,
        "implantology": DentistSpecialization.implantology,
        "radiology": DentistSpecialization.radiology,
    }
    return mapping.get(spec.lower(), DentistSpecialization.general_dentistry)


def _dentist_to_read(d: Dentist, db: Session) -> DentistRead:
    availabilities = db.query(DentistAvailability).filter(DentistAvailability.dentist_id == d.id).all()
    slots = [
        TimeSlot(day_of_week=a.day_of_week, start_time=a.start_time, end_time=a.end_time, is_available=a.is_available)
        for a in availabilities
    ]
    return DentistRead(
        id=d.id,
        slug=d.slug,
        full_name=d.full_name,
        qualification=d.qualification,
        degrees=d.degrees,
        specialization=[d.specialization],
        experience_years=d.experience_years,
        clinic_name=d.clinic_name,
        consultation_fee=d.consultation_fee,
        available_timings=slots,
        languages=d.languages.split(",") if d.languages else [],
        biography=d.biography,
        profile_picture_url=d.profile_picture,
        is_available=d.is_active,
        source_url=d.source_url,
        rating=d.rating,
        review_count=d.total_reviews,
        department=d.department,
        hospital=d.hospital,
        gender=d.gender,
        clinical_interests=d.clinical_interests,
        research_interests=d.research_interests,
        education=d.education,
        consultation_timings=d.consultation_timings,
        available_days=d.available_days,
        appointment_url=d.appointment_url,
        profile_url=d.profile_url,
        image_url=d.image_url,
        image_path=d.image_path,
        data_version=d.data_version,
        last_scraped_at=d.last_scraped_at,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


def _dentist_to_full_read(d: Dentist) -> DentistFullRead:
    return DentistFullRead(
        id=d.id,
        full_name=d.full_name,
        slug=d.slug,
        qualification=d.qualification,
        degrees=d.degrees,
        specialization=d.specialization.value if d.specialization else "",
        department=d.department,
        hospital=d.hospital,
        experience_years=d.experience_years,
        gender=d.gender,
        clinic_name=d.clinic_name,
        clinic_address=d.clinic_address,
        clinic_phone=d.clinic_phone,
        clinic_email=d.clinic_email,
        consultation_fee=d.consultation_fee,
        consultation_timings=d.consultation_timings,
        available_days=d.available_days,
        appointment_url=d.appointment_url,
        languages=d.languages.split(",") if d.languages else [],
        biography=d.biography,
        areas_of_interest=d.areas_of_interest,
        clinical_interests=d.clinical_interests,
        research_interests=d.research_interests,
        education=d.education,
        certifications=d.certifications,
        awards=d.awards,
        publications=d.publications,
        memberships=d.memberships,
        profile_picture=d.profile_picture,
        image_url=d.image_url,
        image_path=d.image_path,
        profile_url=d.profile_url,
        phone=d.phone,
        email=d.email,
        hospital_address=d.hospital_address,
        source_url=d.source_url,
        rating=d.rating,
        total_reviews=d.total_reviews,
        is_active=d.is_active,
        data_version=d.data_version,
        last_scraped_at=d.last_scraped_at,
        created_at=d.created_at,
        updated_at=d.updated_at,
    )


@router.get("", response_model=DentistSearchResult)
def search_dentists(
    params: DentistSearchParams = Depends(),
    db: Session = Depends(get_db),
) -> DentistSearchResult:
    query = db.query(Dentist).filter(Dentist.is_active.is_(True))

    if params.query:
        search = f"%{params.query}%"
        query = query.filter(
            or_(
                Dentist.full_name.ilike(search),
                Dentist.clinic_name.ilike(search),
                Dentist.biography.ilike(search),
                Dentist.clinical_interests.ilike(search),
            )
        )

    if params.specialization:
        query = query.filter(Dentist.specialization == params.specialization)

    if params.clinic:
        query = query.filter(Dentist.clinic_name.ilike(f"%{params.clinic}%"))

    if params.min_experience is not None:
        query = query.filter(Dentist.experience_years >= params.min_experience)

    if params.max_fee is not None:
        query = query.filter(Dentist.consultation_fee <= params.max_fee)

    if params.language:
        query = query.filter(Dentist.languages.ilike(f"%{params.language}%"))

    total = query.count()
    total_pages = (total + params.limit - 1) // params.limit
    offset = (params.page - 1) * params.limit

    dentists = query.order_by(Dentist.rating.desc(), Dentist.full_name).offset(offset).limit(params.limit).all()

    result = [_dentist_to_read(d, db) for d in dentists]

    return DentistSearchResult(
        dentists=result,
        total=total,
        page=params.page,
        limit=params.limit,
        total_pages=total_pages,
    )


@router.get("/search", response_model=DentistSearchResultV2)
def search_dentists_v2(
    query: str | None = None,
    specialization: str | None = None,
    clinic: str | None = None,
    hospital: str | None = None,
    min_experience: int | None = Query(default=None, ge=0),
    max_fee: float | None = Query(default=None, ge=0),
    language: str | None = None,
    gender: str | None = None,
    page: int = Query(default=1, ge=1),
    limit: int = Query(default=10, ge=1, le=50),
    sort_by: str = Query(default="name", pattern="^(name|experience|rating|fee)$"),
    sort_order: str = Query(default="asc", pattern="^(asc|desc)$"),
    db: Session = Depends(get_db),
) -> DentistSearchResultV2:
    q = db.query(Dentist).filter(Dentist.is_active.is_(True))

    if query:
        search = f"%{query}%"
        q = q.filter(
            or_(
                Dentist.full_name.ilike(search),
                Dentist.biography.ilike(search),
                Dentist.clinical_interests.ilike(search),
                Dentist.research_interests.ilike(search),
                Dentist.qualifications.ilike(search),
                Dentist.specialization.ilike(search),
            )
        )

    if specialization:
        spec_enum = _map_specialization(specialization)
        q = q.filter(Dentist.specialization == spec_enum)

    if clinic:
        q = q.filter(Dentist.clinic_name.ilike(f"%{clinic}%"))

    if hospital:
        q = q.filter(Dentist.hospital.ilike(f"%{hospital}%"))

    if min_experience is not None:
        q = q.filter(Dentist.experience_years >= min_experience)

    if max_fee is not None:
        q = q.filter(Dentist.consultation_fee <= max_fee)

    if language:
        q = q.filter(Dentist.languages.ilike(f"%{language}%"))

    if gender:
        q = q.filter(Dentist.gender.ilike(f"%{gender}%"))

    total = q.count()
    total_pages = (total + limit - 1) // limit
    offset = (page - 1) * limit

    sort_col = {
        "name": Dentist.full_name,
        "experience": Dentist.experience_years,
        "rating": Dentist.rating,
        "fee": Dentist.consultation_fee,
    }.get(sort_by, Dentist.full_name)

    if sort_order == "desc":
        sort_col = sort_col.desc()

    dentists = q.order_by(sort_col).offset(offset).limit(limit).all()

    return DentistSearchResultV2(
        dentists=[_dentist_to_full_read(d) for d in dentists],
        total=total,
        page=page,
        limit=limit,
        total_pages=total_pages,
    )


@router.get("/specializations", response_model=list[DentistSpecializationStat])
def list_specializations(db: Session = Depends(get_db)) -> list[DentistSpecializationStat]:
    results = (
        db.query(Dentist.specialization, func.count(Dentist.id))
        .filter(Dentist.is_active.is_(True))
        .group_by(Dentist.specialization)
        .all()
    )
    return [
        DentistSpecializationStat(
            value=spec.value if spec else "general_dentistry",
            label=spec.value.replace("_", " ").title() if spec else "General",
            count=count,
        )
        for spec, count in results
    ]


@router.get("/availability")
def get_availability(
    dentist_id: str = Query(...),
    date: datetime = Query(...),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    dentist = db.get(Dentist, dentist_id)
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist not found")

    day_of_week = date.weekday()
    slots = db.query(DentistAvailability).filter(
        DentistAvailability.dentist_id == dentist_id,
        DentistAvailability.day_of_week == day_of_week,
        DentistAvailability.is_available.is_(True),
    ).all()

    booked = db.query(Appointment).filter(
        Appointment.dentist_id == dentist_id,
        func.date(Appointment.appointment_date) == date.date(),
        Appointment.status.in_([AppointmentStatus.pending, AppointmentStatus.confirmed]),
    ).all()

    booked_times = [(a.appointment_date, a.appointment_date) for a in booked]

    return [
        {
            "start_time": slot.start_time,
            "end_time": slot.end_time,
            "is_booked": any(
                slot.start_time <= b[0].strftime("%H:%M") < slot.end_time for b in booked_times
            ),
        }
        for slot in slots
    ]


@router.get("/{dentist_id}", response_model=DentistRead)
def get_dentist(dentist_id: str, db: Session = Depends(get_db)) -> DentistRead:
    dentist = db.get(Dentist, dentist_id)
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist not found")
    return _dentist_to_read(dentist, db)


@router.post("", response_model=DentistRead, status_code=status.HTTP_201_CREATED)
def create_dentist(
    payload: DentistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DentistRead:
    dentist = Dentist(
        full_name=payload.full_name,
        qualification=payload.qualification,
        degrees=payload.degrees,
        specialization=payload.specialization[0] if payload.specialization else DentistSpecialization.general_dentistry,
        experience_years=payload.experience_years or 0,
        clinic_name=payload.clinic_name,
        consultation_fee=payload.consultation_fee or 0.0,
        languages=",".join(payload.languages) if payload.languages else None,
        biography=payload.biography,
        profile_picture=payload.profile_picture_url,
        is_active=payload.is_available,
        source_url=payload.source_url,
        department=payload.department,
        hospital=payload.hospital,
        gender=payload.gender,
        clinical_interests=payload.clinical_interests,
        research_interests=payload.research_interests,
        education=payload.education,
        profile_url=payload.profile_url,
        image_url=payload.image_url,
    )
    db.add(dentist)
    db.flush()

    for slot in payload.available_timings:
        db.add(DentistAvailability(
            dentist_id=dentist.id,
            day_of_week=slot.day_of_week,
            start_time=slot.start_time,
            end_time=slot.end_time,
            is_available=slot.is_available,
        ))

    db.commit()
    db.refresh(dentist)

    return _dentist_to_read(dentist, db)


@router.patch("/{dentist_id}", response_model=DentistRead)
def update_dentist(
    dentist_id: str,
    payload: DentistUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DentistRead:
    dentist = db.get(Dentist, dentist_id)
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist not found")

    update_data = payload.model_dump(exclude_unset=True)
    if "specialization" in update_data:
        update_data["specialization"] = update_data["specialization"][0] if update_data["specialization"] else None
    if "languages" in update_data:
        update_data["languages"] = ",".join(update_data["languages"]) if update_data["languages"] else None
    if "available_timings" in update_data:
        db.query(DentistAvailability).filter(DentistAvailability.dentist_id == dentist_id).delete()
        for slot in update_data["available_timings"]:
            db.add(DentistAvailability(
                dentist_id=dentist_id,
                day_of_week=slot.day_of_week,
                start_time=slot.start_time,
                end_time=slot.end_time,
                is_available=slot.is_available,
            ))
        del update_data["available_timings"]

    for key, value in update_data.items():
        setattr(dentist, key, value)

    dentist.updated_at = datetime.now()
    db.commit()
    db.refresh(dentist)

    return _dentist_to_read(dentist, db)


@router.delete("/{dentist_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dentist(
    dentist_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> None:
    dentist = db.get(Dentist, dentist_id)
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist not found")
    db.delete(dentist)
    db.commit()


@router.get("/{dentist_id}/availability")
def get_dentist_availability(
    dentist_id: str,
    date: datetime = Query(...),
    db: Session = Depends(get_db),
) -> list[dict[str, Any]]:
    return get_availability(dentist_id=dentist_id, date=date, db=db)


@router.post("/sync")
def sync_dentists(
    payload: SyncRequest = SyncRequest(),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, str]:
    def _run_sync() -> None:
        from app.core.database import SessionLocal
        session = SessionLocal()
        try:
            service = DentistSyncService(session)
            result = service.sync(force=payload.force)
            logger.info(
                "Background sync complete: added=%d updated=%d errors=%d",
                result.added, result.updated, len(result.errors),
            )
        except Exception as exc:
            logger.error("Background sync failed: %s", exc)
        finally:
            session.close()

    background_tasks.add_task(_run_sync)
    return {"status": "sync_started", "force": payload.force}


@router.post("/sync-now", response_model=SyncResultResponse)
def sync_dentists_now(
    payload: SyncRequest = SyncRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> SyncResultResponse:
    service = DentistSyncService(db)
    result = service.sync(force=payload.force)
    return SyncResultResponse(
        added=result.added,
        updated=result.updated,
        unchanged=result.unchanged,
        images_downloaded=result.images_downloaded,
        errors=result.errors,
        elapsed_seconds=result.elapsed_seconds,
        total_profiles=result.total_profiles,
    )


@router.post("/reindex", response_model=dict[str, int])
def reindex_dentists(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict[str, int]:
    from app.services.scraper.embedding_service import DentistEmbeddingService
    service = DentistEmbeddingService(db)
    return service.reindex()


@router.post("/export", response_model=ExportResponse)
def export_dentists(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> ExportResponse:
    from app.services.scraper.export_service import DentistExportService
    service = DentistExportService(db)
    csv_path = service.export_csv()
    json_path = service.export_json()
    total = db.query(func.count(Dentist.id)).scalar() or 0
    return ExportResponse(csv_path=csv_path, json_path=json_path, total_exported=total)
