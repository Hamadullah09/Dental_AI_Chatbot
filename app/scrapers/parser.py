"""AKU dentist profile page parser."""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import get_settings
from app.scrapers.crawler import DoctorListing

logger = logging.getLogger(__name__)


@dataclass
class DentistProfile:
    """Complete parsed dentist profile data."""
    name: str
    profile_id: str
    profile_url: str
    slug: str = ""
    specialty: str = ""
    qualifications: str = ""
    degrees: str = ""
    experience_years: int = 0
    clinic_name: str = "Aga Khan University Hospital"
    department: str = "Dentistry"
    hospital: str = "Aga Khan University Hospital"
    gender: str = ""
    languages: list[str] = field(default_factory=list)
    biography: str = ""
    areas_of_interest: str = ""
    clinical_interests: str = ""
    research_interests: str = ""
    education: str = ""
    certifications: str = ""
    awards: str = ""
    publications: str = ""
    memberships: str = ""
    consultation_timings: str = ""
    available_days: str = ""
    consultation_fee: float = 0.0
    appointment_url: str = ""
    phone: str = ""
    email: str = ""
    hospital_address: str = ""
    clinic_address: str = ""
    image_url: str = ""
    image_path: str = ""
    doctor_code: str = ""
    schedule: list[dict[str, str]] = field(default_factory=list)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")
        if not self.appointment_url and self.doctor_code:
            self.appointment_url = (
                f"https://hospitals.aku.edu/Pakistan/Pages/Request-an-Appointment.aspx"
                f"?DoctorID={self.doctor_code}&CinicLocation=&Speciality=Dentistry"
            )

    def compute_hash(self) -> str:
        import hashlib
        parts = [
            self.name,
            self.qualifications,
            self.specialty,
            self.biography,
            self.consultation_timings,
            self.image_url,
        ]
        combined = "|".join(str(p) for p in parts)
        self.content_hash = hashlib.sha256(combined.encode()).hexdigest()
        return self.content_hash


class ProfileParser:
    """Parses individual AKU dentist profile pages."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.scraper_base_url
        self.schedule_api = self.settings.scraper_schedule_api
        self.user_agent = self.settings.scraper_user_agent
        self.timeout = self.settings.scraper_request_timeout_seconds
        self.max_retries = self.settings.scraper_max_retries
        self.backoff = self.settings.scraper_retry_backoff_multiplier

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }

    def _clean_text(self, text: str) -> str:
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _extract_section(self, soup: BeautifulSoup, label: str) -> str:
        for heading in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
            heading_text = self._clean_text(heading.get_text())
            if label.lower() in heading_text.lower():
                parts: list[str] = []
                for sibling in heading.next_siblings:
                    if isinstance(sibling, Tag):
                        if sibling.name in ("h2", "h3", "h4", "strong", "b"):
                            next_label = self._clean_text(sibling.get_text())
                            if any(kw in next_label.lower() for kw in ["education", "research", "clinical", "publication", "certification", "award", "membership", "interest"]):
                                break
                        text = self._clean_text(sibling.get_text())
                        if text:
                            parts.append(text)
                    elif isinstance(sibling, str):
                        t = sibling.strip()
                        if t:
                            parts.append(t)
                return "; ".join(parts) if parts else ""
        return ""

    def _extract_list_section(self, soup: BeautifulSoup, label: str) -> str:
        for heading in soup.find_all(["h2", "h3", "h4", "strong", "b"]):
            if label.lower() in self._clean_text(heading.get_text()).lower():
                items: list[str] = []
                for sibling in heading.next_siblings:
                    if isinstance(sibling, Tag):
                        if sibling.name in ("ul", "ol"):
                            for li in sibling.find_all("li"):
                                items.append(self._clean_text(li.get_text()))
                        elif sibling.name in ("h2", "h3", "h4"):
                            break
                        else:
                            text = self._clean_text(sibling.get_text())
                            if text:
                                items.append(text)
                return "; ".join(items) if items else ""
        return ""

    def _extract_text_after_label(self, soup: BeautifulSoup, label: str) -> str:
        for elem in soup.find_all(["span", "div", "p", "td", "li"]):
            elem_text = self._clean_text(elem.get_text())
            if elem_text.lower().startswith(label.lower()):
                remaining = elem_text[len(label):].strip(": -")
                if remaining:
                    return remaining
        return ""

    def _parse_profile_page(self, html: str, listing: DoctorListing) -> DentistProfile:
        soup = BeautifulSoup(html, "html.parser")
        profile = DentistProfile(
            name=listing.name,
            profile_id=listing.profile_id,
            profile_url=listing.profile_url,
            slug=listing.slug,
            doctor_code=listing.doctor_code,
            image_url=listing.image_url,
            specialty=listing.specialty or "Dentistry",
        )

        name_tag = soup.select_one("h1, h2.doctor-name, .profile-name")
        if name_tag:
            extracted = self._clean_text(name_tag.get_text())
            if extracted and len(extracted.split()) >= 2 and "contact" not in extracted.lower():
                profile.name = extracted

        img_tags = soup.select("img[src*='Faculty'], img[src*='Attachments'], img.profile-image, img[class*='doctor']")
        for img in img_tags:
            src = img.get("src", "") or img.get("data-src", "")
            if src and isinstance(src, str) and "default_user" not in src:
                profile.image_url = urljoin(self.base_url, src)
                break

        if not profile.image_url:
            profile.image_url = listing.image_url

        profile.qualifications = (
            self._extract_text_after_label(soup, "Qualification")
            or self._extract_text_after_label(soup, "Qualifications")
            or self._extract_section(soup, "Qualification")
        )
        profile.degrees = (
            self._extract_text_after_label(soup, "Degree")
            or self._extract_text_after_label(soup, "Degrees")
        )

        exp_text = (
            self._extract_text_after_label(soup, "Experience")
            or self._extract_text_after_label(soup, "Years of Experience")
        )
        if exp_text:
            digits = re.sub(r"[^\d]", "", exp_text)
            if digits:
                profile.experience_years = int(digits)

        profile.biography = (
            self._extract_text_after_label(soup, "Biography")
            or self._extract_text_after_label(soup, "About")
            or self._extract_section(soup, "Biography")
        )

        profile.clinical_interests = (
            self._extract_text_after_label(soup, "Clinical Interest")
            or self._extract_list_section(soup, "Clinical Interest")
        )
        profile.research_interests = (
            self._extract_text_after_label(soup, "Research Interest")
            or self._extract_list_section(soup, "Research Interest")
        )
        profile.areas_of_interest = (
            self._extract_text_after_label(soup, "Area")
            or self._extract_list_section(soup, "Area of Interest")
        )

        profile.education = (
            self._extract_text_after_label(soup, "Education")
            or self._extract_list_section(soup, "Education")
        )
        profile.certifications = (
            self._extract_text_after_label(soup, "Certification")
            or self._extract_list_section(soup, "Certification")
        )
        profile.awards = (
            self._extract_text_after_label(soup, "Award")
            or self._extract_list_section(soup, "Award")
        )
        profile.publications = (
            self._extract_text_after_label(soup, "Publication")
            or self._extract_list_section(soup, "Publication")
        )
        profile.memberships = (
            self._extract_text_after_label(soup, "Membership")
            or self._extract_list_section(soup, "Membership")
        )

        lang_text = self._extract_text_after_label(soup, "Language")
        if lang_text:
            profile.languages = [l.strip() for l in re.split(r"[,;]", lang_text) if l.strip()]

        gender_text = self._extract_text_after_label(soup, "Gender")
        if gender_text:
            profile.gender = gender_text.lower()
        else:
            name_lower = profile.name.lower()
            if any(name_lower.startswith(p) for p in ("mr.", "dr.", "prof.")):
                profile.gender = "male"

        email_tag = soup.select_one("a[href^='mailto:']")
        if email_tag:
            href = email_tag.get("href", "")
            if isinstance(href, str):
                profile.email = href.replace("mailto:", "").strip()

        phone_tag = soup.select_one("a[href^='tel:']")
        if phone_tag:
            href = phone_tag.get("href", "")
            if isinstance(href, str):
                profile.phone = href.replace("tel:", "").strip()

        address_tag = soup.select_one("[class*='address'], [class*='location']")
        if address_tag:
            profile.clinic_address = self._clean_text(address_tag.get_text())

        profile.consultation_timings = self._extract_text_after_label(soup, "Timing") or self._extract_text_after_label(soup, "Consultation")
        profile.available_days = self._extract_text_after_label(soup, "Available Day")

        profile.compute_hash()
        return profile

    def fetch_schedule(self, doctor_code: str, specialty: str = "Dentistry") -> list[dict[str, str]]:
        if not doctor_code:
            return []
        try:
            url = f"{self.schedule_api}?DoctorID={doctor_code}&CinicLocation=&Speciality={specialty}"
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.get(url, headers={"Accept": "application/json"})
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    return [
                        {
                            "clinic": item.get("Clinicname", ""),
                            "day": item.get("ClinicDay", ""),
                            "start_time": item.get("ClinicStartTime", ""),
                            "end_time": item.get("ClinicEndTime", ""),
                        }
                        for item in data
                    ]
        except Exception as exc:
            logger.warning("Failed to fetch schedule for %s: %s", doctor_code, exc)
        return []

    def parse_profile(self, listing: DoctorListing, client: httpx.Client | None = None) -> DentistProfile | None:
        if not listing.profile_url:
            logger.warning("No profile URL for %s, skipping", listing.name)
            return None

        own_client = client is None
        if own_client:
            client = httpx.Client(
                headers=self._build_headers(),
                timeout=self.timeout,
                follow_redirects=True,
            )

        try:
            for attempt in range(self.max_retries):
                try:
                    resp = client.get(listing.profile_url)  # type: ignore[union-attr]
                    resp.raise_for_status()
                    html = resp.text
                    break
                except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                    if attempt < self.max_retries - 1:
                        wait = self.settings.scraper_request_delay_seconds * (self.backoff ** attempt)
                        logger.warning("Profile fetch error for %s (attempt %d): %s", listing.name, attempt + 1, exc)
                        time.sleep(wait)
                    else:
                        logger.error("Failed to fetch profile for %s after %d attempts: %s", listing.name, self.max_retries, exc)
                        return None

            profile = self._parse_profile_page(html, listing)  # type: ignore[arg-type]

            if listing.doctor_code:
                profile.schedule = self.fetch_schedule(listing.doctor_code)
                if profile.schedule:
                    days = sorted(set(s["day"] for s in profile.schedule if s.get("day")))
                    profile.available_days = ", ".join(days) if days else ""
                    timings = [f"{s['day']}: {s['start_time']}-{s['end_time']}" for s in profile.schedule if s.get("day")]
                    profile.consultation_timings = "; ".join(timings) if timings else ""

            return profile
        finally:
            if own_client and client:
                client.close()

    def parse_all(self, listings: list[DoctorListing]) -> list[DentistProfile]:
        profiles: list[DentistProfile] = []
        delay = self.settings.scraper_request_delay_seconds

        with httpx.Client(
            headers=self._build_headers(),
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            for i, listing in enumerate(listings):
                if i > 0:
                    time.sleep(delay)
                profile = self.parse_profile(listing, client)
                if profile:
                    profiles.append(profile)
                    logger.info("Parsed profile %d/%d: %s", i + 1, len(listings), profile.name)
                else:
                    logger.warning("Skipped profile %d/%d: %s", i + 1, len(listings), listing.name)

        logger.info("Successfully parsed %d/%d profiles", len(profiles), len(listings))
        return profiles
