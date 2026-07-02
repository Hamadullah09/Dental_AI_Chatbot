from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from app.core.config import get_settings
from app.schemas import SourceCitation


@dataclass
class WebSearchResult:
    title: str
    url: str
    content: str
    score: float | None = None

    def to_citation(self) -> SourceCitation:
        return SourceCitation(
            source_type="web",
            document_name=self.title or urlparse(self.url).netloc,
            url=self.url,
            score=self.score,
        )


class WebSearchService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.trusted_domains = self.settings.web_search_domain_list

    @property
    def is_configured(self) -> bool:
        provider = self.settings.web_search_provider.lower().strip()
        if provider == "tavily":
            return bool(self.settings.tavily_api_key)
        if provider == "brave":
            return bool(self.settings.brave_search_api_key)
        if provider == "google":
            return bool(self.settings.google_search_api_key and self.settings.google_search_engine_id)
        return False

    def search(self, query: str) -> list[WebSearchResult]:
        provider = self.settings.web_search_provider.lower().strip()
        if provider == "google":
            return self._search_google(query)
        if provider == "brave":
            return self._search_brave(query)
        return self._search_tavily(query)

    def _search_google(self, query: str) -> list[WebSearchResult]:
        if not self.settings.google_search_api_key or not self.settings.google_search_engine_id:
            return []
        params = {
            "key": self.settings.google_search_api_key,
            "cx": self.settings.google_search_engine_id,
            "q": query,
            "num": min(self.settings.web_search_max_results, 10),
            "safe": "active",
        }
        with httpx.Client(timeout=20, trust_env=False) as client:
            response = client.get("https://www.googleapis.com/customsearch/v1", params=params)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code
                if status == 403:
                    raise RuntimeError("Google Custom Search API returned 403. Enable Custom Search API and check API key restrictions/quota.") from exc
                if status == 400:
                    raise RuntimeError("Google Custom Search API returned 400. Check GOOGLE_SEARCH_ENGINE_ID and query settings.") from exc
                raise RuntimeError(f"Google Custom Search API returned HTTP {status}.") from exc
            data = response.json()
        results = []
        for item in data.get("items", []):
            url = str(item.get("link") or "")
            if not self._is_trusted_url(url):
                continue
            content = str(item.get("snippet") or "").strip()
            if not content:
                continue
            results.append(
                WebSearchResult(
                    title=str(item.get("title") or urlparse(url).netloc),
                    url=url,
                    content=content[:1800],
                )
            )
        return results

    def _search_tavily(self, query: str) -> list[WebSearchResult]:
        if not self.settings.tavily_api_key:
            return []
        payload = {
            "api_key": self.settings.tavily_api_key,
            "query": query,
            "search_depth": "advanced",
            "max_results": self.settings.web_search_max_results,
            "include_domains": self.trusted_domains,
            "include_answer": False,
            "include_raw_content": False,
        }
        with httpx.Client(timeout=20, trust_env=False) as client:
            response = client.post("https://api.tavily.com/search", json=payload)
            response.raise_for_status()
            data = response.json()
        results = []
        for item in data.get("results", []):
            url = str(item.get("url") or "")
            if not self._is_trusted_url(url):
                continue
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            results.append(
                WebSearchResult(
                    title=str(item.get("title") or urlparse(url).netloc),
                    url=url,
                    content=content[:1800],
                    score=float(item["score"]) if item.get("score") is not None else None,
                )
            )
        return results

    def _search_brave(self, query: str) -> list[WebSearchResult]:
        if not self.settings.brave_search_api_key:
            return []
        domain_query = " OR ".join(f"site:{domain}" for domain in self.trusted_domains)
        params = {
            "q": f"{query} ({domain_query})",
            "count": min(self.settings.web_search_max_results, 10),
            "text_decorations": False,
        }
        headers = {"X-Subscription-Token": self.settings.brave_search_api_key}
        with httpx.Client(timeout=20, trust_env=False) as client:
            response = client.get("https://api.search.brave.com/res/v1/web/search", params=params, headers=headers)
            response.raise_for_status()
            data = response.json()
        results = []
        for item in data.get("web", {}).get("results", []):
            url = str(item.get("url") or "")
            if not self._is_trusted_url(url):
                continue
            content = str(item.get("description") or "").strip()
            if not content:
                continue
            results.append(
                WebSearchResult(
                    title=str(item.get("title") or urlparse(url).netloc),
                    url=url,
                    content=content[:1800],
                )
            )
        return results

    def _is_trusted_url(self, url: str) -> bool:
        host = urlparse(url).netloc.lower()
        if not host:
            return False
        return any(host == domain or host.endswith(f".{domain}") for domain in self.trusted_domains)
