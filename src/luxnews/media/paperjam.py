from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from bs4 import BeautifulSoup

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class PaperjamMediaScraper(BaseMediaScraper):
    SEARCH_URL_BASE = (
        "https://paperjam.lu/search?numericRefinementList%5BpublicationDate%5D={publication_date}"
    )
    MAX_SEARCH_PAGES = 8
    SEARCH_CARD_SELECTORS = [
        ".search_results-item",
        ".search__results-item",
        "article.search_results-item",
    ]
    DATE_PATTERN = re.compile(r"\b(\d{1,2}\.\d{1,2}\.\d{4})\b")

    def requires_selenium_search(self) -> bool:
        return True

    def build_search_urls(self, keyword: str) -> list[str]:
        publication_filter = self.resolve_publication_filter(self.config.last_days)
        encoded_filter = quote(publication_filter, safe="")
        base_url = self.SEARCH_URL_BASE.format(publication_date=encoded_filter)

        urls = [base_url]
        for page in range(2, self.MAX_SEARCH_PAGES + 1):
            urls.append(f"{base_url}&page={page}")
        return urls

    def resolve_publication_filter(self, last_days: int) -> str:
        if last_days <= 1:
            return "Aujourd'hui"
        if last_days <= 2:
            return "Depuis hier"
        return "Depuis une semaine"

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        cards = self._select_search_cards(soup)
        hits: list[SearchHit] = []

        for card in cards:
            link = card.select_one("a[href]")
            if not link:
                continue
            href = link.get("href")
            if not href:
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            hits.append(
                SearchHit(
                    url=url,
                    title=self._extract_card_title(card, link),
                    published_at=self._parse_search_date(self._extract_date_text(card)),
                    snippet=self._extract_card_snippet(card),
                    media_id=self.definition.media_id,
                )
            )

        return hits

    def _select_search_cards(self, soup: BeautifulSoup) -> list:
        for selector in self.SEARCH_CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                return cards
        return []

    def _extract_card_title(self, card, link) -> Optional[str]:
        title_node = card.select_one("h4.news-card__title, h3.news-card__title")
        if title_node:
            title = title_node.get("title") or title_node.get_text(strip=True)
            if title:
                return title
        link_title = link.get("title") or link.get_text(strip=True)
        return link_title or None

    def _extract_date_text(self, element) -> Optional[str]:
        if hasattr(element, "select_one"):
            info = element.select_one(".informations")
            if info:
                return info.get_text(" ", strip=True)
            time_node = element.select_one("time")
            if time_node:
                return time_node.get("datetime") or time_node.get_text(" ", strip=True)
        return super()._extract_date_text(element)

    def _extract_card_snippet(self, card) -> Optional[str]:
        snippet_node = card.select_one(".news-card__excerpt, p")
        if not snippet_node:
            return None
        snippet = snippet_node.get_text(" ", strip=True)
        return snippet or None

    def _parse_search_date(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None

        normalized = " ".join(raw.split())
        date_match = self.DATE_PATTERN.search(normalized)
        if date_match:
            try:
                parsed = datetime.strptime(date_match.group(1), "%d.%m.%Y")
            except ValueError:
                parsed = None
            if parsed:
                return parsed.replace(tzinfo=timezone.utc)

        return parse_date(normalized)
