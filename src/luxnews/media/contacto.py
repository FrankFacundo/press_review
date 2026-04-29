from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class ContactoMediaScraper(BaseMediaScraper):
    SEARCH_CARD_SELECTORS = [
        "article",
        ".post",
        ".search-result",
        ".article-item",
        ".news-item",
        ".entry",
        "li.result",
    ]
    DATE_PATTERN = re.compile(r"\b(\d{1,2})[./\-](\d{1,2})[./\-](\d{4})\b")

    def requires_browser_search(self) -> bool:
        return True

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        # Try __NEXT_DATA__ first (Mediahuis Next.js platform, same as wort.lu)
        hits = self._parse_next_data(html, base_url)
        if hits:
            return hits
        # Fall back to generic HTML parsing
        return self._parse_html(html, base_url)

    # ------------------------------------------------------------------
    # __NEXT_DATA__ strategy (shared Mediahuis platform with wort.lu)
    # ------------------------------------------------------------------

    def _parse_next_data(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        next_data = soup.find("script", id="__NEXT_DATA__")
        if not next_data:
            return []

        raw_payload = next_data.string or next_data.get_text()
        if not raw_payload:
            return []

        try:
            payload = json.loads(raw_payload)
        except json.JSONDecodeError:
            return []

        if not isinstance(payload, dict):
            return []

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
                    title=self._extract_next_title(item),
                    published_at=self._extract_next_date(item),
                    snippet=self._extract_next_snippet(item),
                    media_id=self.definition.media_id,
                )
            )
        return hits

    def _extract_next_title(self, item: dict) -> Optional[str]:
        raw = item.get("title")
        if isinstance(raw, str):
            title = " ".join(raw.split())
            if title:
                return title
        return None

    def _extract_next_date(self, item: dict) -> Optional[datetime]:
        for key in ("published", "updated", "lastModified"):
            raw = item.get(key)
            if isinstance(raw, str) and raw.strip():
                parsed = parse_date(raw)
                if parsed:
                    return parsed
        return None

    def _extract_next_snippet(self, item: dict) -> Optional[str]:
        for key in ("intro", "teaserIntro", "excerpt"):
            raw = item.get(key)
            if isinstance(raw, str):
                text = " ".join(raw.split())
                if text:
                    return text
        return None

    # ------------------------------------------------------------------
    # Generic HTML strategy (fallback)
    # ------------------------------------------------------------------

    def _parse_html(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        cards = self._select_cards(soup)
        hits: list[SearchHit] = []
        seen_urls: set[str] = set()

        for card in cards:
            link = card.select_one("h1 a[href], h2 a[href], h3 a[href], a[href]")
            if not link:
                continue
            href = (link.get("href") or "").strip()
            if not href:
                continue
            url = to_absolute_url(base_url, href)
            if url in seen_urls:
                continue
            if not self._is_allowed_url(url):
                continue

            title_node = card.select_one("h1, h2, h3")
            title = " ".join((title_node or link).get_text(" ", strip=True).split()) or None

            date_text = self._extract_date_text(card)
            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    published_at=self._parse_search_date(date_text),
                    snippet=self._extract_card_snippet(card),
                    media_id=self.definition.media_id,
                )
            )
            seen_urls.add(url)

        return hits

    def _select_cards(self, soup: BeautifulSoup) -> list:
        for selector in self.SEARCH_CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                return cards
        return []

    def _extract_date_text(self, element) -> Optional[str]:
        if hasattr(element, "select_one"):
            time_node = element.select_one("time")
            if time_node:
                return time_node.get("datetime") or time_node.get_text(" ", strip=True)
            for selector in (".date", ".post-date", "[class*='date']", ".published", "span.meta"):
                node = element.select_one(selector)
                if not node:
                    continue
                value = " ".join(node.get_text(" ", strip=True).split())
                if value:
                    return value
        return super()._extract_date_text(element)

    def _extract_card_snippet(self, card) -> Optional[str]:
        snippet_node = card.select_one(".excerpt, .entry-summary, .teaser, p")
        if not snippet_node:
            return None
        return " ".join(snippet_node.get_text(" ", strip=True).split()) or None

    def _parse_search_date(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None
        normalized = " ".join(raw.split())
        match = self.DATE_PATTERN.search(normalized)
        if match:
            day, month, year = int(match.group(1)), int(match.group(2)), int(match.group(3))
            try:
                return datetime(year, month, day, tzinfo=timezone.utc)
            except ValueError:
                pass
        return parse_date(normalized)
