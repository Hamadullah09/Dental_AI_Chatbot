"""AKU Dentistry listing page crawler with pagination support."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Tag

from app.core.config import get_settings

logger = logging.getLogger(__name__)

_DAY_NAME_MAP = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass
class DoctorListing:
    """A single doctor entry discovered on the listing page."""
    name: str
    profile_id: str
    profile_url: str
    specialty: str = ""
    image_url: str = ""
    doctor_code: str = ""
    slug: str = ""

    def __post_init__(self) -> None:
        if not self.slug:
            self.slug = re.sub(r"[^a-z0-9]+", "-", self.name.lower()).strip("-")


@dataclass
class CrawlResult:
    """Result of a full crawl of the listing page."""
    listings: list[DoctorListing] = field(default_factory=list)
    pages_crawled: int = 0
    total_found: int = 0
    errors: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0


class AKUCrawler:
    """Crawls the AKU Find a Doctor dentistry listing and discovers all profile URLs."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.base_url = self.settings.scraper_base_url
        self.listing_url = self.settings.scraper_dentistry_url
        self.user_agent = self.settings.scraper_user_agent
        self.request_delay = self.settings.scraper_request_delay_seconds
        self.timeout = self.settings.scraper_request_timeout_seconds
        self.max_retries = self.settings.scraper_max_retries
        self.backoff_multiplier = self.settings.scraper_retry_backoff_multiplier
        self.items_per_page = self.settings.scraper_images_per_page
        self.max_pages = self.settings.scraper_max_pages

    def _build_headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Connection": "keep-alive",
        }

    def _extract_profile_id(self, url: str) -> str:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        return params.get("ProfileID", [""])[0]

    def _extract_doctor_code(self, element: Tag) -> str:
        for attr in ("ng-click", "onclick", "data-doctor-id"):
            val = element.get(attr, "")
            if val and isinstance(val, str):
                match = re.search(r"['\"]([A-Z]{4})['\"]", val)
                if match:
                    return match.group(1)
        return ""

    def _parse_listing_page(self, html: str) -> list[DoctorListing]:
        soup = BeautifulSoup(html, "html.parser")
        listings: list[DoctorListing] = []

        cards = soup.select(".u-info-v1-2")
        if not cards:
            cards = soup.select("[class*='u-info']")

        for card in cards:
            try:
                name_tag = card.select_one("h4, h3, .g-color-black")
                if not name_tag:
                    continue
                name = name_tag.get_text(strip=True)
                if not name:
                    continue

                spec_tag = card.select_one(".ProfileSpeciality em, .ProfileSpeciality, em")
                specialty = spec_tag.get_text(strip=True) if spec_tag else ""

                img_tag = card.select_one("img")
                image_url = ""
                if img_tag:
                    raw_src = img_tag.get("src", "") or img_tag.get("data-src", "")
                    if raw_src and isinstance(raw_src, str):
                        image_url = urljoin(self.base_url, raw_src)

                link_tag = card.select_one("a[id*='ahreftitle'], a[href*='profiles.aspx']")
                profile_url = ""
                profile_id = ""
                if link_tag:
                    href = link_tag.get("href", "")
                    if href and isinstance(href, str):
                        profile_url = urljoin(self.base_url, href)
                        profile_id = self._extract_profile_id(profile_url)

                if not profile_id:
                    profile_id_attr = card.get("id", "")
                    if profile_id_attr and isinstance(profile_id_attr, str):
                        match = re.search(r"ProfileID[=:](\d+)", profile_id_attr)
                        if match:
                            profile_id = match.group(1)

                if not profile_id and name:
                    profile_id = hashlib.md5(name.encode()).hexdigest()[:8]

                doctor_code = self._extract_doctor_code(card)

                listings.append(DoctorListing(
                    name=name,
                    profile_id=profile_id,
                    profile_url=profile_url,
                    specialty=specialty,
                    image_url=image_url,
                    doctor_code=doctor_code,
                ))
            except Exception as exc:
                logger.warning("Failed to parse card: %s", exc)
                continue

        return listings

    def _get_total_pages(self, html: str) -> int:
        soup = BeautifulSoup(html, "html.parser")
        page_links = soup.select("table[id*='dlPaging'] td a")
        max_page = 1
        for link in page_links:
            text = link.get_text(strip=True)
            if text.isdigit():
                max_page = max(max_page, int(text))
        return max_page

    def _get_next_page_url(self, html: str) -> str | None:
        soup = BeautifulSoup(html, "html.parser")
        next_btn = soup.select_one("a.plastschild:not(.aspNetDisabled), a[id*='lbtnNext']:not(.aspNetDisabled)")
        if next_btn:
            href = next_btn.get("href", "")
            if href and isinstance(href, str) and "doPostBack" not in href:
                return urljoin(self.base_url, href)
        return None

    def _extract_postback_data(self, html: str) -> dict[str, str]:
        soup = BeautifulSoup(html, "html.parser")
        data: dict[str, str] = {}
        for inp in soup.select("input[type='hidden']"):
            name = inp.get("name", "")
            value = inp.get("value", "")
            if name and isinstance(value, str):
                data[name] = value
        return data

    def _build_postback_payload(self, html: str, target: str, event_arg: str = "") -> dict[str, str]:
        data = self._extract_postback_data(html)
        data["__EVENTTARGET"] = target
        data["__EVENTARGUMENT"] = event_arg
        return data

    def crawl_page(self, client: httpx.Client, url: str) -> tuple[str, list[DoctorListing], int]:
        for attempt in range(self.max_retries):
            try:
                response = client.get(url, follow_redirects=True)
                response.raise_for_status()
                html = response.text
                listings = self._parse_listing_page(html)
                total_pages = self._get_total_pages(html)
                return html, listings, total_pages
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    wait = self.request_delay * (self.backoff_multiplier ** attempt)
                    logger.warning("Rate limited, waiting %.1fs", wait)
                    time.sleep(wait)
                    continue
                logger.error("HTTP error on %s: %s", url, exc)
                raise
            except (httpx.ConnectError, httpx.ReadTimeout) as exc:
                wait = self.request_delay * (self.backoff_multiplier ** attempt)
                logger.warning("Network error (attempt %d/%d), retrying in %.1fs: %s", attempt + 1, self.max_retries, wait, exc)
                time.sleep(wait)
                continue
        raise RuntimeError(f"Failed to crawl {url} after {self.max_retries} attempts")

    def crawl_postback_page(self, client: httpx.Client, url: str, html: str, target: str) -> tuple[str, list[DoctorListing]]:
        payload = self._build_postback_payload(html, target)
        for attempt in range(self.max_retries):
            try:
                response = client.post(url, data=payload, follow_redirects=True)
                response.raise_for_status()
                new_html = response.text
                listings = self._parse_listing_page(new_html)
                return new_html, listings
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                wait = self.request_delay * (self.backoff_multiplier ** attempt)
                logger.warning("Postback error (attempt %d/%d): %s", attempt + 1, self.max_retries, exc)
                time.sleep(wait)
                continue
        raise RuntimeError(f"Failed postback to {target} after {self.max_retries} attempts")

    def crawl_all(self) -> CrawlResult:
        result = CrawlResult()
        start = time.monotonic()

        headers = self._build_headers()
        timeout_config = httpx.Timeout(self.timeout, connect=10.0)

        with httpx.Client(headers=headers, timeout=timeout_config) as client:
            logger.info("Crawling listing page: %s", self.listing_url)
            html, listings, total_pages = self.crawl_page(client, self.listing_url)
            result.listings.extend(listings)
            result.pages_crawled = 1

            pages_to_crawl = min(total_pages, self.max_pages)
            logger.info("Found %d pages total, will crawl %d", total_pages, pages_to_crawl)

            for page_num in range(2, pages_to_crawl + 1):
                time.sleep(self.request_delay)
                try:
                    target = f"ctl00$ctl57$g_60566fe0_dc1c_4691_b069_68c42408d9a2$ctl00$dlPaging$ctl{page_num - 1:02d}$lnkbtnPaging"
                    new_html, page_listings = self.crawl_postback_page(
                        client, self.listing_url, html, target
                    )
                    html = new_html
                    result.listings.extend(page_listings)
                    result.pages_crawled += 1
                    logger.info("Page %d: found %d doctors", page_num, len(page_listings))
                except Exception as exc:
                    msg = f"Failed to crawl page {page_num}: {exc}"
                    logger.error(msg)
                    result.errors.append(msg)

        result.total_found = len(result.listings)
        result.elapsed_seconds = time.monotonic() - start
        logger.info(
            "Crawl complete: %d dentists found across %d pages in %.1fs",
            result.total_found,
            result.pages_crawled,
            result.elapsed_seconds,
        )
        return result
