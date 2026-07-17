"""Download and store dentist profile images."""

from __future__ import annotations

import hashlib
import logging
import re
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ImageDownloader:
    """Downloads dentist profile images to local storage."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self.images_dir = Path(self.settings.scraper_images_dir)
        self.images_dir.mkdir(parents=True, exist_ok=True)
        self.user_agent = self.settings.scraper_user_agent
        self.timeout = self.settings.scraper_request_timeout_seconds
        self.max_retries = self.settings.scraper_max_retries
        self.backoff = self.settings.scraper_retry_backoff_multiplier
        self.request_delay = self.settings.scraper_request_delay_seconds

    def _get_filename(self, image_url: str, name: str) -> str:
        parsed = urlparse(image_url)
        path_part = unquote(parsed.path)
        ext = Path(path_part).suffix or ".jpg"
        safe_name = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
        return f"{safe_name}{ext}"

    def download_single(self, client: httpx.Client, image_url: str, name: str) -> str | None:
        if not image_url:
            return None

        filename = self._get_filename(image_url, name)
        dest = self.images_dir / filename

        if dest.exists():
            return str(dest)

        for attempt in range(self.max_retries):
            try:
                resp = client.get(image_url)
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "image" not in content_type and len(resp.content) < 100:
                    logger.warning("URL %s did not return an image (content-type: %s)", image_url, content_type)
                    return None
                dest.write_bytes(resp.content)
                logger.info("Downloaded image: %s -> %s", image_url, dest)
                return str(dest)
            except (httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout) as exc:
                if attempt < self.max_retries - 1:
                    wait = self.request_delay * (self.backoff ** attempt)
                    logger.warning("Image download error for %s (attempt %d): %s", name, attempt + 1, exc)
                    time.sleep(wait)
                else:
                    logger.error("Failed to download image for %s: %s", name, exc)
                    return None
        return None

    def download_all(self, profiles: list[dict[str, str]]) -> dict[str, str]:
        """Download images for a list of profiles.

        Args:
            profiles: List of dicts with 'name' and 'image_url' keys.

        Returns:
            Dict mapping name to local image path.
        """
        results: dict[str, str] = {}
        with httpx.Client(
            headers={"User-Agent": self.user_agent},
            timeout=self.timeout,
            follow_redirects=True,
        ) as client:
            for i, profile in enumerate(profiles):
                name = profile.get("name", "")
                image_url = profile.get("image_url", "")
                if not image_url or not name:
                    continue
                if i > 0:
                    time.sleep(self.request_delay)
                path = self.download_single(client, image_url, name)
                if path:
                    results[name] = path

        logger.info("Downloaded %d/%d images", len(results), len(profiles))
        return results
