"""Tests for the AKU dentist profile parser."""

from __future__ import annotations

import pytest

from app.scrapers.crawler import DoctorListing
from app.scrapers.parser import DentistProfile, ProfileParser


class TestDentistProfile:
    def test_slug_generation(self) -> None:
        profile = DentistProfile(
            name="Dr. Test Doctor",
            profile_id="123",
            profile_url="https://example.com",
        )
        assert profile.slug == "dr-test-doctor"

    def test_custom_slug(self) -> None:
        profile = DentistProfile(
            name="Test",
            profile_id="123",
            profile_url="https://example.com",
            slug="custom",
        )
        assert profile.slug == "custom"

    def test_appointment_url_generation(self) -> None:
        profile = DentistProfile(
            name="Test",
            profile_id="123",
            profile_url="https://example.com",
            doctor_code="TSTI",
        )
        assert "DoctorID=TSTI" in profile.appointment_url
        assert "Request-an-Appointment" in profile.appointment_url

    def test_compute_hash(self) -> None:
        profile = DentistProfile(
            name="Test",
            profile_id="123",
            profile_url="https://example.com",
            qualifications="BDS",
        )
        h = profile.compute_hash()
        assert len(h) == 64  # SHA-256 hex digest
        assert profile.content_hash == h

    def test_compute_hash_deterministic(self) -> None:
        p1 = DentistProfile(name="A", profile_id="1", profile_url="", qualifications="BDS")
        p2 = DentistProfile(name="A", profile_id="1", profile_url="", qualifications="BDS")
        assert p1.compute_hash() == p2.compute_hash()


class TestProfileParser:
    def setup_method(self) -> None:
        self.parser = ProfileParser()

    def test_clean_text(self) -> None:
        assert self.parser._clean_text("  hello   world  ") == "hello world"

    def test_parse_profile_page_minimal(self) -> None:
        html = "<html><body><h1>Dr. Test</h1></body></html>"
        listing = DoctorListing(name="Dr. Test", profile_id="1", profile_url="https://example.com")
        profile = self.parser._parse_profile_page(html, listing)
        assert profile.name == "Dr. Test"
        assert profile.profile_id == "1"
        assert profile.specialty == "Dentistry"

    def test_parse_profile_page_with_biography(self) -> None:
        html = """
        <html><body>
        <h1>Dr. Test</h1>
        <h3>Biography</h3>
        <p>Dr. Test is a experienced dentist.</p>
        </body></html>
        """
        listing = DoctorListing(name="Dr. Test", profile_id="1", profile_url="https://example.com")
        profile = self.parser._parse_profile_page(html, listing)
        assert "experienced dentist" in profile.biography

    def test_extract_email(self) -> None:
        html = '<html><body><a href="mailto:test@example.com">Email</a></body></html>'
        listing = DoctorListing(name="Test", profile_id="1", profile_url="https://example.com")
        profile = self.parser._parse_profile_page(html, listing)
        assert profile.email == "test@example.com"

    def test_extract_phone(self) -> None:
        html = '<html><body><a href="tel:+921234567890">Phone</a></body></html>'
        listing = DoctorListing(name="Test", profile_id="1", profile_url="https://example.com")
        profile = self.parser._parse_profile_page(html, listing)
        assert profile.phone == "+921234567890"
