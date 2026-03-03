from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class InfogreenMediaScraper(BaseMediaScraper):
    DATE_PATTERN = re.compile(r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b")

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        cards = soup.select("div.result-card")
        hits: list[SearchHit] = []

        for card in cards:
            link = card.select_one("h3 a[href]")
            if not link:
                link = card.select_one("a[href]")
            if not link:
                continue

            href = link.get("href")
            if not href:
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            title = link.get_text(strip=True) or None
            published_at = self._parse_card_date(card)
            snippet = self._extract_card_snippet(card)

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

    def _parse_card_date(self, card) -> Optional[datetime]:
        date_span = card.select_one("span.date")
        if date_span:
            raw = date_span.get_text(strip=True)
            match = self.DATE_PATTERN.search(raw)
            if match:
                try:
                    return datetime.strptime(match.group(1), "%d.%m.%Y").replace(
                        tzinfo=timezone.utc
                    )
                except ValueError:
                    pass
            parsed = parse_date(raw)
            if parsed:
                return parsed
        return None

    def _extract_card_snippet(self, card) -> Optional[str]:
        p_tag = card.select_one("p")
        if p_tag:
            text = p_tag.get_text(" ", strip=True)
            if text:
                return text
        return None
