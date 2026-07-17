"""Dentist synchronization service with conflict resolution."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import Dentist, DentistAvailability, DentistSpecialization
from app.repositories.dentist_repo import DentistRepository
from app.scrapers.crawler import AKUCrawler, CrawlResult
from app.scrapers.image_downloader import ImageDownloader
from app.scrapers.parser import DentistProfile, ProfileParser

logger = logging.getLogger(__name__)

_DAY_NAME_MAP = {
    "monday": 0, "tuesday": 1, "wednesday": 2,
    "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
}

_SPEC_MAP = {
    "dentistry": DentistSpecialization.general_dentistry,
    "orthodontics": DentistSpecialization.orthodontics,
    "periodontics": DentistSpecialization.periodontics,
    "endodontics": DentistSpecialization.endodontics,
    "prosthodontics": DentistSpecialization.prosthodontics,
    "oral surgery": DentistSpecialization.oral_surgery,
    "pediatric": DentistSpecialization.pediatric_dentistry,
    "pedodontics": DentistSpecialization.pediatric_dentistry,
    "cosmetic": DentistSpecialization.cosmetic_dentistry,
    "implantology": DentistSpecialization.implantology,
    "radiology": DentistSpecialization.radiology,
    "general": DentistSpecialization.general_dentistry,
}


def _map_specialization(spec: str) -> DentistSpecialization:
    spec_lower = spec.lower().strip()
    # Check more specific matches first
    for key in ["pediatric", "pedodontics", "oral surgery", "cosmetic", "orthodontics",
                 "periodontics", "endodontics", "prosthodontics", "implantology",
                 "radiology", "dentistry", "general"]:
        if key in spec_lower:
            return _SPEC_MAP[key]
    return DentistSpecialization.general_dentistry


def _parse_availability(schedule: list[dict[str, str]]) -> list[dict]:
    slots = []
    for entry in schedule:
        day_name = entry.get("day", "").lower()
        day_of_week = _DAY_NAME_MAP.get(day_name, -1)
        if day_of_week == -1:
            continue
        start = entry.get("start_time", "")
        end = entry.get("end_time", "")
        if start and end:
            slots.append({
                "day_of_week": day_of_week,
                "start_time": start[:5],
                "end_time": end[:5],
                "is_available": True,
            })
    return slots


@dataclass
class SyncResult:
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    images_downloaded: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    total_profiles: int = 0


class DentistSyncService:
    """Orchestrates the full crawl -> parse -> download -> sync pipeline."""

    def __init__(self, db: Session) -> None:
        self.db = db
        self.repo = DentistRepository(db)
        self.crawler = AKUCrawler()
        self.parser = ProfileParser()
        self.downloader = ImageDownloader()
        self.settings = get_settings()

    def _profile_to_dict(self, profile: DentistProfile, image_path: str | None = None) -> dict:
        spec = _map_specialization(profile.specialty or "Dentistry")
        avail = _parse_availability(profile.schedule)
        return {
            "name": profile.name,
            "slug": profile.slug,
            "qualifications": profile.qualifications,
            "degrees": profile.degrees,
            "specialization": spec,
            "sub_specialization": "",
            "department": profile.department or "Dentistry",
            "hospital": profile.hospital or "Aga Khan University Hospital",
            "experience_years": profile.experience_years,
            "gender": profile.gender,
            "clinic_name": profile.clinic_name or "Aga Khan University Hospital",
            "clinic_address": profile.clinic_address,
            "consultation_fee": profile.consultation_fee,
            "consultation_timings": profile.consultation_timings,
            "available_days": profile.available_days,
            "appointment_url": profile.appointment_url,
            "languages": profile.languages,
            "biography": profile.biography,
            "areas_of_interest": profile.areas_of_interest,
            "clinical_interests": profile.clinical_interests,
            "research_interests": profile.research_interests,
            "education": profile.education,
            "certifications": profile.certifications,
            "awards": profile.awards,
            "publications": profile.publications,
            "memberships": profile.memberships,
            "image_url": profile.image_url,
            "image_path": image_path or "",
            "profile_url": profile.profile_url,
            "phone": profile.phone,
            "email": profile.email,
            "hospital_address": profile.hospital_address,
            "source_url": self.settings.scraper_dentistry_url,
            "content_hash": profile.content_hash,
            "availability_slots": avail,
        }

    def sync(self, force: bool = False) -> SyncResult:
        start = time.monotonic()
        result = SyncResult()

        logger.info("Starting dentist synchronization (force=%s)", force)

        try:
            crawl_result = self.crawler.crawl_all()
            result.total_profiles = crawl_result.total_found
            if crawl_result.errors:
                result.errors.extend(crawl_result.errors)
        except Exception as exc:
            result.errors.append(f"Crawl failed: {exc}")
            result.elapsed_seconds = time.monotonic() - start
            return result

        if not crawl_result.listings:
            result.elapsed_seconds = time.monotonic() - start
            return result

        profiles = self.parser.parse_all(crawl_result.listings)

        image_data = [
            {"name": p.name, "image_url": p.image_url}
            for p in profiles if p.image_url
        ]
        downloaded = self.downloader.download_all(image_data)
        result.images_downloaded = len(downloaded)

        for idx, profile in enumerate(profiles):
            try:
                image_path = downloaded.get(profile.name)
                data = self._profile_to_dict(profile, image_path)

                existing = self.repo.find_existing(
                    profile_url=profile.profile_url,
                    name=profile.name,
                )

                if not force and existing and existing.content_hash == profile.content_hash:
                    result.unchanged += 1
                    continue

                self.repo.upsert_from_scraped(data)
                self.db.flush()

                if existing:
                    result.updated += 1
                else:
                    result.added += 1

                if (idx + 1) % 10 == 0:
                    self.db.commit()
                    logger.info("Committed batch at profile %d/%d", idx + 1, len(profiles))
            except Exception as exc:
                msg = f"Failed to sync {profile.name}: {exc}"
                logger.error(msg, exc_info=True)
                result.errors.append(msg)
                try:
                    self.db.rollback()
                except Exception:
                    pass

        try:
            if self.db.is_active:
                self.db.commit()
            count = self.db.execute(text("SELECT count(*) FROM dentists")).scalar()
            logger.info("After commit: %d dentists in DB", count)
        except Exception as exc:
            logger.error("Failed to commit sync results: %s", exc, exc_info=True)
            result.errors.append(f"Commit failed: {exc}")
            try:
                self.db.rollback()
            except Exception:
                pass
        result.elapsed_seconds = time.monotonic() - start
        logger.info(
            "Sync complete: added=%d updated=%d unchanged=%d images=%d errors=%d in %.1fs",
            result.added, result.updated, result.unchanged,
            result.images_downloaded, len(result.errors), result.elapsed_seconds,
        )
        return result
