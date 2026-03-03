from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class RTLMediaScraper(BaseMediaScraper):
    DATE_FMT_SEARCH = "%d.%m.%Y"
    API_TEMPLATE = "https://www-api.rtl.lu/search?q={query}&p={page}"

    def prefers_plain_search(self) -> bool:
        return True

    def build_search_urls(self, keyword: str) -> list[str]:
        query = quote_plus(keyword)
        return [
            self.API_TEMPLATE.format(query=query, page=page)
            for page in range(1, self.config.max_pages + 1)
        ]

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        payload = self._extract_json_payload(html)
        results = payload.get("content", {}).get("results", [])
        if isinstance(results, list):
            hits = self._build_hits_from_results(results, base_url)
            if hits:
                return hits
        return super().parse_search_results(html, base_url)

    def extract_date(self, html: str) -> datetime | None:  # noqa: D401
        soup = BeautifulSoup(html, "lxml")
        time_tag = soup.find("time")
        if time_tag and time_tag.has_attr("datetime"):
            try:
                value = time_tag["datetime"].replace("Z", "+00:00")
                return datetime.fromisoformat(value)
            except ValueError:  # malformed datetime
                pass

        date_tag = soup.select_one("a.rtl-search-res_date")
        if date_tag:
            try:
                return datetime.strptime(date_tag.get_text(strip=True), self.DATE_FMT_SEARCH)
            except ValueError:
                pass
        return None

    def _extract_date_text(self, element) -> Optional[str]:
        extracted = self.extract_date(str(element))
        if extracted:
            return extracted.isoformat()

        if hasattr(element, "parents"):
            for parent in element.parents:
                extracted = self.extract_date(str(parent))
                if extracted:
                    return extracted.isoformat()

        return super()._extract_date_text(element)

    def _extract_json_payload(self, html: str) -> dict:
        try:
            payload = json.loads(html)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _build_hits_from_results(self, results: list[dict], base_url: str) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for item in results:
            if not isinstance(item, dict):
                continue

            href = item.get("url")
            if not isinstance(href, str) or not href.strip():
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            published_at = None
            raw_date = item.get("publishDate")
            if isinstance(raw_date, str) and raw_date.strip():
                published_at = parse_date(raw_date)
            if published_at is None:
                continue

            raw_title = item.get("title")
            title = None
            if isinstance(raw_title, str):
                title = " ".join(raw_title.split()) or None

            snippet = None
            for key in ("header", "kicker"):
                raw_snippet = item.get(key)
                if not isinstance(raw_snippet, str):
                    continue
                cleaned = " ".join(raw_snippet.split())
                if cleaned:
                    snippet = cleaned
                    break

            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    published_at=published_at,
                    snippet=snippet,
                    media_id=self.definition.media_id,
                )
            )
        return hits
