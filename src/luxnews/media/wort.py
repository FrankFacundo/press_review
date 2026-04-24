from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class WortMediaScraper(BaseMediaScraper):
    def prepare_article_for_pdf(self, driver) -> None:
        script = """
if (document.documentElement) {
  document.documentElement.style.setProperty("overflow-x", "hidden", "important");
}
if (document.body) {
  // Shrink the article frame so content does not bleed to the page edges
  // in the exported PDF. Also reserve top space for the PDF header stamp.
  document.body.style.setProperty("max-width", "1400px", "important");
  document.body.style.setProperty("margin-left", "auto", "important");
  document.body.style.setProperty("margin-right", "auto", "important");
  document.body.style.setProperty("padding-left", "24px", "important");
  document.body.style.setProperty("padding-right", "24px", "important");
  document.body.style.setProperty("padding-top", "40px", "important");
  document.body.style.setProperty("box-sizing", "border-box", "important");
  document.body.style.setProperty("overflow-x", "hidden", "important");
}
"""
        try:
            driver.execute_script(script)
        except WebDriverException:
            return

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        payload = self._extract_next_data_payload(html)
        results = (
            payload.get("props", {})
            .get("pageProps", {})
            .get("data", {})
            .get("results", [])
        )

        if not isinstance(results, list):
            return []

        hits: list[SearchHit] = []
        for item in results:
            if not isinstance(item, dict):
                continue

            href = item.get("href")
            if not isinstance(href, str) or not href.strip():
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            hits.append(
                SearchHit(
                    url=url,
                    title=self._extract_title(item),
                    published_at=self._extract_published_at(item),
                    snippet=self._extract_snippet(item),
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

    def _extract_title(self, item: dict) -> Optional[str]:
        raw_title = item.get("title")
        if isinstance(raw_title, str):
            title = " ".join(raw_title.split())
            if title:
                return title

        fields = item.get("fields")
        if isinstance(fields, dict):
            fallback_title = fields.get("title")
            if isinstance(fallback_title, str):
                title = " ".join(fallback_title.split())
                if title:
                    return title
        return None

    def _extract_published_at(self, item: dict) -> Optional[datetime]:
        for key in ("published", "updated", "lastModified"):
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                parsed = parse_date(raw)
                if parsed:
                    return parsed
        return None

    def _extract_snippet(self, item: dict) -> Optional[str]:
        for key in ("intro", "teaserIntro", "teaserHeadline"):
            snippet = self._extract_story_text(item.get(key))
            if snippet:
                return snippet
        return None

    def _extract_story_text(self, payload) -> Optional[str]:
        if isinstance(payload, str):
            text = " ".join(payload.split())
            return text or None

        if isinstance(payload, list):
            parts = [part for part in (self._extract_story_text(item) for item in payload) if part]
            if parts:
                return " ".join(parts)
            return None

        if isinstance(payload, dict):
            fields = payload.get("fields")
            if isinstance(fields, list):
                parts: list[str] = []
                for field in fields:
                    if not isinstance(field, dict):
                        continue
                    raw_value = field.get("value")
                    if not isinstance(raw_value, str):
                        continue
                    value = " ".join(raw_value.split())
                    if value:
                        parts.append(value)
                if parts:
                    return " ".join(parts)

            for key in ("value", "text"):
                raw_value = payload.get(key)
                if isinstance(raw_value, str):
                    value = " ".join(raw_value.split())
                    if value:
                        return value
        return None
