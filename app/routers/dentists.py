from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.deps import get_current_user, require_admin
from app.models import Appointment, Dentist, DentistAvailability, DentistSpecialization, User, UserRole
from app.schemas import (
    AppointmentStatus,
    DentistCreate,
    DentistRead,
    DentistSearchParams,
    DentistSearchResult,
    DentistUpdate,
    TimeSlot,
)

router = APIRouter(prefix="/dentists", tags=["dentists"])


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

    result = []
    for d in dentists:
        availabilities = db.query(DentistAvailability).filter(DentistAvailability.dentist_id == d.id).all()
        slots = [
            TimeSlot(day_of_week=a.day_of_week, start_time=a.start_time, end_time=a.end_time, is_available=a.is_available)
            for a in availabilities
        ]
        result.append(
            DentistRead(
                id=d.id,
                full_name=d.full_name,
                qualification=d.qualification,
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
                created_at=d.created_at,
                updated_at=d.updated_at,
            )
        )

    return DentistSearchResult(
        dentists=result,
        total=total,
        page=params.page,
        limit=params.limit,
        total_pages=total_pages,
    )


@router.get("/specializations", response_model=list[dict[str, str]])
def list_specializations() -> list[dict[str, str]]:
    return [
        {"value": s.value, "label": s.value.replace("_", " ").title()}
        for s in DentistSpecialization
    ]


@router.get("/{dentist_id}", response_model=DentistRead)
def get_dentist(dentist_id: str, db: Session = Depends(get_db)) -> DentistRead:
    dentist = db.get(Dentist, dentist_id)
    if not dentist:
        raise HTTPException(status_code=404, detail="Dentist not found")

    availabilities = db.query(DentistAvailability).filter(DentistAvailability.dentist_id == dentist.id).all()
    slots = [
        TimeSlot(day_of_week=a.day_of_week, start_time=a.start_time, end_time=a.end_time, is_available=a.is_available)
        for a in availabilities
    ]

    return DentistRead(
        id=dentist.id,
        full_name=dentist.full_name,
        qualification=dentist.qualification,
        specialization=[dentist.specialization],
        experience_years=dentist.experience_years,
        clinic_name=dentist.clinic_name,
        consultation_fee=dentist.consultation_fee,
        available_timings=slots,
        languages=dentist.languages.split(",") if dentist.languages else [],
        biography=dentist.biography,
        profile_picture_url=dentist.profile_picture,
        is_available=dentist.is_active,
        source_url=dentist.source_url,
        rating=dentist.rating,
        review_count=dentist.total_reviews,
        created_at=dentist.created_at,
        updated_at=dentist.updated_at,
    )


@router.get("/{dentist_id}/availability")
def get_dentist_availability(
    dentist_id: str,
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


@router.post("", response_model=DentistRead, status_code=status.HTTP_201_CREATED)
def create_dentist(
    payload: DentistCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> DentistRead:
    dentist = Dentist(
        full_name=payload.full_name,
        qualification=payload.qualification,
        specialization=payload.specialization[0] if payload.specialization else DentistSpecialization.general_dentistry,
        experience_years=payload.experience_years or 0,
        clinic_name=payload.clinic_name,
        consultation_fee=payload.consultation_fee or 0.0,
        languages=",".join(payload.languages) if payload.languages else None,
        biography=payload.biography,
        profile_picture=payload.profile_picture_url,
        is_active=payload.is_available,
        source_url=payload.source_url,
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

    return get_dentist(dentist.id, db)


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

    return get_dentist(dentist.id, db)


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


@router.post("/sync-aku")
def sync_aku_dentists(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
) -> dict:
    import httpx
    from bs4 import BeautifulSoup

    url = "https://hospitals.aku.edu/pakistan/patientservices/pages/findadoctor.aspx?Spec=Dentistry"
    try:
        response = httpx.get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        doctors = []
        cards = soup.select(".doctor-card, .provider-card, .card, tr")
        for card in cards:
            try:
                name_elem = card.select_one(".doctor-name, .name, h3, h4, .title")
                name = name_elem.get_text(strip=True) if name_elem else None

                spec_elem = card.select_one(".specialty, .specialization, .spec")
                specialization = spec_elem.get_text(strip=True) if spec_elem else "General Dentistry"

                exp_elem = card.select_one(".experience, .years")
                experience = exp_elem.get_text(strip=True) if exp_elem else "0"

                clinic_elem = card.select_one(".clinic, .location, .hospital")
                clinic = clinic_elem.get_text(strip=True) if clinic_elem else "AKU Hospital"

                img_elem = card.select_one("img")
                picture = img_elem.get("src") if img_elem else None

                if name:
                    exp_years = int("".join(filter(str.isdigit, experience))) if experience else 0
                    mapped_spec = _map_specialization(specialization)

                    existing = db.query(Dentist).filter(
                        Dentist.full_name == name,
                        Dentist.source_url == url,
                    ).first()

                    if not existing:
                        dentist = Dentist(
                            full_name=name,
                            specialization=mapped_spec,
                            experience_years=exp_years,
                            clinic_name=clinic,
                            profile_picture=picture,
                            source_url=url,
                            is_active=True,
                            is_verified=True,
                        )
                        db.add(dentist)
                        doctors.append(name)
            except Exception:
                continue

        db.commit()
        return {"synced": len(doctors), "doctors": doctors}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")