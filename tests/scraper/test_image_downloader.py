"""Tests for the image downloader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.scrapers.image_downloader import ImageDownloader


class TestImageDownloader:
    def setup_method(self) -> None:
        self.downloader = ImageDownloader()

    def test_get_filename(self) -> None:
        url = "https://hospitals.aku.edu/pakistan/patientservices/Lists/Faculty/Attachments/829/Dr%20Abdul.jpeg"
        filename = self.downloader._get_filename(url, "Dr. Abdul Ghani Shaikh")
        assert filename.endswith(".jpeg")
        assert "dr_abdul_ghani_shaikh" in filename

    def test_get_filename_no_ext(self) -> None:
        url = "https://example.com/image"
        filename = self.downloader._get_filename(url, "Test Doctor")
        assert filename.endswith(".jpg")
        assert "test_doctor" in filename

    def test_get_filename_custom_ext(self) -> None:
        url = "https://example.com/photo.png"
        filename = self.downloader._get_filename(url, "Dr. Smith")
        assert filename.endswith(".png")
