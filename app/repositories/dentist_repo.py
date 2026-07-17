"""Dentist repository for database operations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models import Dentist, DentistAvailability, DentistSpecialization

logger = logging.getLogger(__name__)


class DentistRepository:
    """Data access layer for the Dentist model."""

    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_profile_url(self, profile_url: str) -> Dentist | None:
        return self.db.query(Dentist).filter(Dentist.profile_url == profile_url).first()

    def get_by_content_hash(self, content_hash: str) -> Dentist | None:
        return self.db.query(Dentist).filter(Dentist.content_hash == content_hash).first()

    def get_by_name(self, name: str) -> Dentist | None:
        return self.db.query(Dentist).filter(Dentist.full_name == name).first()

    def get_by_slug(self, slug: str) -> Dentist | None:
        return self.db.query(Dentist).filter(Dentist.slug == slug).first()

    def get_by_id(self, dentist_id: str) -> Dentist | None:
        return self.db.query(Dentist).filter(Dentist.id == dentist_id).first()

    def list_all(self, active_only: bool = True) -> list[Dentist]:
        query = self.db.query(Dentist)
        if active_only:
            query = query.filter(Dentist.is_active.is_(True))
        return query.order_by(Dentist.full_name).all()

    def search(
        self,
        query: str | None = None,
        specialization: DentistSpecialization | None = None,
        clinic: str | None = None,
        min_experience: int | None = None,
        language: str | None = None,
        page: int = 1,
        limit: int = 10,
    ) -> tuple[list[Dentist], int]:
        q = self.db.query(Dentist).filter(Dentist.is_active.is_(True))

        if query:
            search = f"%{query}%"
            q = q.filter(
                or_(
                    Dentist.full_name.ilike(search),
                    Dentist.biography.ilike(search),
                    Dentist.clinical_interests.ilike(search),
                    Dentist.specialization.ilike(search),
                    Dentist.qualifications.ilike(search),
                )
            )
        if specialization:
            q = q.filter(Dentist.specialization == specialization)
        if clinic:
            q = q.filter(Dentist.clinic_name.ilike(f"%{clinic}%"))
        if min_experience is not None:
            q = q.filter(Dentist.experience_years >= min_experience)
        if language:
            q = q.filter(Dentist.languages.ilike(f"%{language}%"))

        total = q.count()
        offset = (page - 1) * limit
        dentists = q.order_by(Dentist.full_name).offset(offset).limit(limit).all()
        return dentists, total

    def find_existing(self, profile_url: str | None = None, name: str | None = None) -> Dentist | None:
        if profile_url:
            existing = self.get_by_profile_url(profile_url)
            if existing:
                return existing
        if name:
            return self.get_by_name(name)
        return None

    def upsert_from_scraped(self, data: dict) -> Dentist:
        existing = self.find_existing(
            profile_url=data.get("profile_url"),
            name=data.get("name"),
        )

        if existing:
            for key, value in data.items():
                if key == "name":
                    continue
                if value is not None and value != "" and value != 0 and value != 0.0:
                    setattr(existing, key, value)
            existing.is_active = True
            existing.is_verified = True
            existing.data_version += 1
            existing.last_scraped_at = datetime.now(timezone.utc)
            self.db.flush()
            logger.info("Updated dentist: %s (v%d)", existing.full_name, existing.data_version)
            return existing

        dentist = Dentist(
            full_name=data.get("name", ""),
            slug=data.get("slug", ""),
            qualification=data.get("qualifications", ""),
            degrees=data.get("degrees", ""),
            specialization=data.get("specialization", DentistSpecialization.general_dentistry),
            sub_specialization=data.get("sub_specialization", ""),
            department=data.get("department", "Dentistry"),
            hospital=data.get("hospital", "Aga Khan University Hospital"),
            experience_years=data.get("experience_years", 0),
            gender=data.get("gender", ""),
            clinic_name=data.get("clinic_name", "Aga Khan University Hospital"),
            clinic_address=data.get("clinic_address", ""),
            consultation_fee=data.get("consultation_fee", 0.0),
            consultation_timings=data.get("consultation_timings", ""),
            available_days=data.get("available_days", ""),
            appointment_url=data.get("appointment_url", ""),
            languages=",".join(data.get("languages", [])) if isinstance(data.get("languages"), list) else data.get("languages", ""),
            biography=data.get("biography", ""),
            areas_of_interest=data.get("areas_of_interest", ""),
            clinical_interests=data.get("clinical_interests", ""),
            research_interests=data.get("research_interests", ""),
            education=data.get("education", ""),
            certifications=data.get("certifications", ""),
            awards=data.get("awards", ""),
            publications=data.get("publications", ""),
            memberships=data.get("memberships", ""),
            profile_picture=data.get("image_url", ""),
            image_url=data.get("image_url", ""),
            image_path=data.get("image_path", ""),
            profile_url=data.get("profile_url", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            hospital_address=data.get("hospital_address", ""),
            source_url=data.get("source_url", ""),
            content_hash=data.get("content_hash", ""),
            data_version=1,
            last_scraped_at=datetime.now(timezone.utc),
            is_active=True,
            is_verified=True,
        )
        self.db.add(dentist)
        self.db.flush()

        for slot_data in data.get("availability_slots", []):
            db_slot = DentistAvailability(
                dentist_id=dentist.id,
                day_of_week=slot_data["day_of_week"],
                start_time=slot_data["start_time"],
                end_time=slot_data["end_time"],
                is_available=slot_data.get("is_available", True),
            )
            self.db.add(db_slot)

        logger.info("Created dentist: %s", dentist.full_name)
        return dentist

    def count_all(self) -> int:
        return self.db.query(func.count(Dentist.id)).scalar() or 0

    def count_active(self) -> int:
        return self.db.query(func.count(Dentist.id)).filter(Dentist.is_active.is_(True)).scalar() or 0

    def get_specializations(self) -> list[dict[str, str | int]]:
        results = (
            self.db.query(Dentist.specialization, func.count(Dentist.id))
            .filter(Dentist.is_active.is_(True))
            .group_by(Dentist.specialization)
            .all()
        )
        return [
            {"value": spec.value if spec else "general_dentistry", "label": spec.value.replace("_", " ").title() if spec else "General", "count": count}
            for spec, count in results
        ]
