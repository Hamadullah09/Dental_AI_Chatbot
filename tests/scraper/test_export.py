"""Tests for the dentist export service."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.models import Dentist, DentistSpecialization


def _make_mock_dentist() -> MagicMock:
    d = MagicMock(spec=Dentist)
    d.id = "test-id"
    d.full_name = "Dr. Test"
    d.slug = "dr-test"
    d.qualification = "BDS"
    d.degrees = "BDS, MDS"
    d.specialization = DentistSpecialization.general_dentistry
    d.department = "Dentistry"
    d.hospital = "AKU"
    d.experience_years = 10
    d.gender = "male"
    d.clinic_name = "AKU Clinic"
    d.clinic_address = "Karachi"
    d.consultation_fee = 5000.0
    d.consultation_timings = ""
    d.available_days = ""
    d.appointment_url = ""
    d.languages = "English,Urdu"
    d.biography = "Test bio"
    d.areas_of_interest = ""
    d.clinical_interests = ""
    d.research_interests = ""
    d.education = ""
    d.certifications = ""
    d.awards = ""
    d.publications = ""
    d.memberships = ""
    d.image_url = ""
    d.image_path = ""
    d.profile_url = "https://example.com"
    d.phone = ""
    d.email = ""
    d.hospital_address = ""
    d.clinic_phone = ""
    d.clinic_email = ""
    d.source_url = ""
    d.content_hash = "abc123"
    d.data_version = 1
    d.is_active = True
    d.rating = 0.0
    d.total_reviews = 0
    d.profile_picture = ""
    d.created_at = MagicMock(isoformat=lambda: "2025-01-01T00:00:00")
    d.updated_at = MagicMock(isoformat=lambda: "2025-01-01T00:00:00")
    d.last_scraped_at = None
    return d


class TestDentistExportCSV:
    def test_export_creates_csv(self, tmp_path: Path) -> None:
        from app.services.scraper.export_service import DentistExportService

        mock_db = MagicMock()
        mock_dentist = _make_mock_dentist()

        service = object.__new__(DentistExportService)
        service.db = mock_db
        service.repo = MagicMock()
        service.repo.list_all.return_value = [mock_dentist]
        service.settings = MagicMock()
        service.output_dir = tmp_path

        csv_path = tmp_path / "dentists.csv"
        result = service.export_csv(csv_path)
        assert Path(result).exists()

        with open(csv_path, newline="") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["name"] == "Dr. Test"

    def test_export_empty(self, tmp_path: Path) -> None:
        from app.services.scraper.export_service import DentistExportService

        mock_db = MagicMock()
        service = object.__new__(DentistExportService)
        service.db = mock_db
        service.repo = MagicMock()
        service.repo.list_all.return_value = []
        service.settings = MagicMock()
        service.output_dir = tmp_path

        csv_path = tmp_path / "empty.csv"
        result = service.export_csv(csv_path)
        assert Path(result).exists()


class TestDentistExportJSON:
    def test_export_creates_json(self, tmp_path: Path) -> None:
        from app.services.scraper.export_service import DentistExportService

        mock_db = MagicMock()
        mock_dentist = _make_mock_dentist()

        service = object.__new__(DentistExportService)
        service.db = mock_db
        service.repo = MagicMock()
        service.repo.list_all.return_value = [mock_dentist]
        service.settings = MagicMock()
        service.output_dir = tmp_path

        json_path = tmp_path / "dentists.json"
        result = service.export_json(json_path)
        assert Path(result).exists()

        with open(json_path) as f:
            data = json.load(f)
            assert len(data) == 1
            assert data[0]["name"] == "Dr. Test"
