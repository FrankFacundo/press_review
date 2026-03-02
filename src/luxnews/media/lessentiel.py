from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class LessentielMediaScraper(BaseMediaScraper):
    def requires_selenium_search(self) -> bool:
        # Search results are rendered by client-side state and require a logged-in session.
        return True

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        payload = self._extract_next_data_payload(html)
        teasers = (
            payload.get("props", {})
            .get("pageProps", {})
            .get("store", {})
            .get("pageData", {})
            .get("data", {})
            .get("teasers", [])
        )

        if not isinstance(teasers, list):
            return []

        hits: list[SearchHit] = []
        for teaser in teasers:
            if not isinstance(teaser, dict):
                continue

            href = teaser.get("url")
            if not isinstance(href, str) or not href.strip():
                continue

            url = to_absolute_url(base_url, href)
            if "/story/" not in url:
                continue
            if not self._is_allowed_url(url):
                continue

            hits.append(
                SearchHit(
                    url=url,
                    title=self._extract_title(teaser),
                    published_at=self._extract_published_at(teaser),
                    snippet=self._extract_snippet(teaser),
                    media_id=self.definition.media_id,
                )
            )
        return hits

    def _extract_next_data_payload(self, html: str) -> dict:
        soup = BeautifulSoup(html, "lxml")
        next_data = soup.find("script", id="__NEXT_DATA__")
        if not next_data:
            return {}

        raw_payload = next_data.string or next_data.get_text()
        if not raw_payload:
            return {}

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return {}

        return payload if isinstance(payload, dict) else {}

    def _extract_title(self, teaser: dict) -> Optional[str]:
        for key in ("title", "titleHeader"):
            raw = teaser.get(key)
            if isinstance(raw, str):
                title = " ".join(raw.split())
                if title:
                    return title
        return None

    def _extract_published_at(self, teaser: dict) -> Optional[datetime]:
        for key in ("published", "updated"):
            raw = teaser.get(key)
            if isinstance(raw, str) and raw.strip():
                parsed = parse_date(raw)
                if parsed:
                    return parsed
        return None

    def _extract_snippet(self, teaser: dict) -> Optional[str]:
        raw = teaser.get("lead")
        if isinstance(raw, str):
            snippet = " ".join(raw.split())
            if snippet:
                return snippet
        return None
