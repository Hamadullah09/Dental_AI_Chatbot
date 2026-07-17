"""Tests for the dentist sync service."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.scrapers.crawler import CrawlResult, DoctorListing
from app.scrapers.parser import DentistProfile
from app.services.scraper.sync_service import (
    DentistSyncService,
    SyncResult,
    _map_specialization,
    _parse_availability,
)
from app.models import DentistSpecialization


class TestMapSpecialization:
    def test_dentistry(self) -> None:
        assert _map_specialization("Dentistry") == DentistSpecialization.general_dentistry

    def test_orthodontics(self) -> None:
        assert _map_specialization("Orthodontics") == DentistSpecialization.orthodontics

    def test_unknown(self) -> None:
        assert _map_specialization("Unknown Speciality") == DentistSpecialization.general_dentistry

    def test_case_insensitive(self) -> None:
        assert _map_specialization("PERIODONTICS") == DentistSpecialization.periodontics

    def test_partial_match(self) -> None:
        assert _map_specialization("Pediatric Dentistry") == DentistSpecialization.pediatric_dentistry


class TestParseAvailability:
    def test_empty(self) -> None:
        assert _parse_availability([]) == []

    def test_valid_schedule(self) -> None:
        schedule = [
            {"day": "Monday", "start_time": "09:00", "end_time": "17:00"},
            {"day": "Tuesday", "start_time": "10:00", "end_time": "16:00"},
        ]
        slots = _parse_availability(schedule)
        assert len(slots) == 2
        assert slots[0]["day_of_week"] == 0
        assert slots[0]["start_time"] == "09:00"
        assert slots[1]["day_of_week"] == 1

    def test_invalid_day(self) -> None:
        schedule = [{"day": "Funday", "start_time": "09:00", "end_time": "17:00"}]
        assert _parse_availability(schedule) == []


class TestSyncResult:
    def test_defaults(self) -> None:
        result = SyncResult()
        assert result.added == 0
        assert result.updated == 0
        assert result.errors == []
        assert result.elapsed_seconds == 0.0
