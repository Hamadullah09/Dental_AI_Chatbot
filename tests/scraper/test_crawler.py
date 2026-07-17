"""Tests for the AKU dentist crawler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.scrapers.crawler import AKUCrawler, CrawlResult, DoctorListing


class TestDoctorListing:
    def test_slug_generation(self) -> None:
        listing = DoctorListing(name="Dr. Abdul Ghani Shaikh", profile_id="829", profile_url="https://example.com")
        assert listing.slug == "dr-abdul-ghani-shaikh"

    def test_slug_custom(self) -> None:
        listing = DoctorListing(name="Ali Sadiq", profile_id="74", profile_url="https://example.com", slug="custom-slug")
        assert listing.slug == "custom-slug"

    def test_empty_name(self) -> None:
        listing = DoctorListing(name="", profile_id="1", profile_url="")
        assert listing.slug == ""


class TestAKUCrawler:
    def setup_method(self) -> None:
        self.crawler = AKUCrawler()

    def test_extract_profile_id_from_url(self) -> None:
        url = "https://hospitals.aku.edu/pakistan/patientservices/pages/profiles.aspx?ProfileID=829&Name=Test&page=findadoctor"
        assert self.crawler._extract_profile_id(url) == "829"

    def test_extract_profile_id_empty(self) -> None:
        assert self.crawler._extract_profile_id("https://example.com") == ""

    def test_build_headers(self) -> None:
        headers = self.crawler._build_headers()
        assert "User-Agent" in headers
        assert "DentalAIChatbot" in headers["User-Agent"]

    def test_parse_listing_page_no_cards(self) -> None:
        html = "<html><body><div>No cards here</div></body></html>"
        listings = self.crawler._parse_listing_page(html)
        assert listings == []

    def test_parse_listing_page_with_cards(self) -> None:
        html = """
        <html><body>
        <div class="u-info-v1-2">
            <h4 class="h5 g-color-black g-mb-5 truncate-text">Dr. Test Doctor</h4>
            <div class="ProfileSpeciality"><em>Dentistry</em></div>
            <a id="ahreftitle1" href="profiles.aspx?ProfileID=999&Name=Test&page=findadoctor">Profile</a>
            <img src="/images/test.jpg" id="imgfaculty1" />
        </div>
        </body></html>
        """
        listings = self.crawler._parse_listing_page(html)
        assert len(listings) == 1
        assert listings[0].name == "Dr. Test Doctor"
        assert listings[0].profile_id == "999"
        assert listings[0].specialty == "Dentistry"

    def test_get_total_pages(self) -> None:
        html = """
        <html><body>
        <table id="dlPaging">
            <tr>
                <td><a class="selecteditem">1</a></td>
                <td><a class="pagginga">2</a></td>
                <td><a class="pagginga">3</a></td>
            </tr>
        </table>
        </body></html>
        """
        assert self.crawler._get_total_pages(html) == 3

    def test_get_total_pages_single(self) -> None:
        html = "<html><body><p>No pagination</p></body></html>"
        assert self.crawler._get_total_pages(html) == 1

    def test_crawl_result_defaults(self) -> None:
        result = CrawlResult()
        assert result.listings == []
        assert result.pages_crawled == 0
        assert result.errors == []
