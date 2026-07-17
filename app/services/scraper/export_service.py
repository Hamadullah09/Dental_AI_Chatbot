"""CSV and JSON export services for dentist data."""

from __future__ import annotations

import csv
import json
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Dentist
from app.repositories.dentist_repo import DentistRepository

logger = logging.getLogger(__name__)


class DentistExportService:
    """Export dentist records to CSV and JSON files."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DentistRepository(db)
        self.settings = get_settings()
        self.output_dir = Path(self.settings.scraper_output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _dentist_to_dict(self, d: Dentist) -> dict:
        return {
            "id": d.id,
            "name": d.full_name,
            "slug": d.slug,
            "qualifications": d.qualification,
            "degrees": d.degrees,
            "specialization": d.specialization.value if d.specialization else "",
            "department": d.department,
            "hospital": d.hospital,
            "experience_years": d.experience_years,
            "gender": d.gender,
            "clinic_name": d.clinic_name,
            "clinic_address": d.clinic_address,
            "consultation_fee": d.consultation_fee,
            "consultation_timings": d.consultation_timings,
            "available_days": d.available_days,
            "appointment_url": d.appointment_url,
            "languages": d.languages,
            "biography": d.biography,
            "areas_of_interest": d.areas_of_interest,
            "clinical_interests": d.clinical_interests,
            "research_interests": d.research_interests,
            "education": d.education,
            "certifications": d.certifications,
            "awards": d.awards,
            "publications": d.publications,
            "memberships": d.memberships,
            "image_url": d.image_url,
            "image_path": d.image_path,
            "profile_url": d.profile_url,
            "phone": d.phone,
            "email": d.email,
            "hospital_address": d.hospital_address,
            "content_hash": d.content_hash,
            "data_version": d.data_version,
            "is_active": d.is_active,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
            "last_scraped_at": d.last_scraped_at.isoformat() if d.last_scraped_at else None,
        }

    def export_csv(self, path: str | Path | None = None) -> str:
        path = Path(path) if path else Path(self.settings.scraper_csv_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        dentists = self.repo.list_all(active_only=False)
        if not dentists:
            logger.warning("No dentists to export")
            return str(path)

        headers = list(self._dentist_to_dict(dentists[0]).keys())
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=headers)
            writer.writeheader()
            for d in dentists:
                writer.writerow(self._dentist_to_dict(d))

        logger.info("Exported %d dentists to %s", len(dentists), path)
        return str(path)

    def export_json(self, path: str | Path | None = None) -> str:
        path = Path(path) if path else Path(self.settings.scraper_json_path)
        path.parent.mkdir(parents=True, exist_ok=True)

        dentists = self.repo.list_all(active_only=False)
        data = [self._dentist_to_dict(d) for d in dentists]

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

        logger.info("Exported %d dentists to %s", len(dentists), path)
        return str(path)
