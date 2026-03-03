from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

import requests

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date

LOGGER = logging.getLogger(__name__)

# today.rtl.lu -> today-api.rtl.lu, infos.rtl.lu -> infos-api.rtl.lu
_API_TEMPLATE = "https://{subdomain}-api.rtl.lu/search?q={query}&p={page}"


class TodayRTLMediaScraper(BaseMediaScraper):
    def prefers_plain_search(self) -> bool:
        return True

    def build_search_urls(self, keyword: str) -> list[str]:
        subdomain = self.definition.domain.split(".")[0]
        query = quote_plus(keyword)
        return [
            _API_TEMPLATE.format(subdomain=subdomain, query=query, page=page)
            for page in range(1, self.config.max_pages + 1)
        ]

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        import json

        try:
            data = json.loads(html)
        except (json.JSONDecodeError, ValueError):
            return []

        results = data.get("content", {}).get("results", [])
        if not isinstance(results, list):
            return []

        hits: list[SearchHit] = []
        for item in results:
            if not isinstance(item, dict):
                continue

            url = item.get("url")
            if not isinstance(url, str) or not url.strip():
                continue

            if not self._is_allowed_url(url):
                continue

            title = item.get("title")
            if isinstance(title, str):
                title = " ".join(title.split()) or None
            else:
                title = None

            published_at = None
            raw_date = item.get("publishDate")
            if isinstance(raw_date, str) and raw_date.strip():
                published_at = parse_date(raw_date)

            if published_at is None:
                continue

            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    published_at=published_at,
                    snippet=item.get("kicker"),
                    media_id=self.definition.media_id,
                )
            )

        return hits

    def fetch_search_page(self, url: str) -> str:
        headers = {
            "User-Agent": self._user_agent(),
            "Accept": "application/json",
        }
        for attempt in range(1, 4):
            try:
                response = requests.get(url, headers=headers, timeout=self.config.request_timeout)
                response.raise_for_status()
                return response.text
            except requests.RequestException as exc:
                LOGGER.warning("Search fetch failed (%s/%s) for %s: %s", attempt, 3, url, exc)
                time.sleep(2**attempt)
        raise RuntimeError(f"Failed to fetch search page: {url}")
