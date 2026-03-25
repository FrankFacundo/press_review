from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Iterable, Optional
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup

from luxnews.config import RunConfig
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url

LOGGER = logging.getLogger(__name__)


class BaseMediaScraper:
    def __init__(self, definition, config: RunConfig):
        self.definition = definition
        self.config = config

    def requires_selenium_search(self) -> bool:
        return False

    def prefers_plain_search(self) -> bool:
        return False

    def prepare_article_for_pdf(self, driver) -> None:
        return

    def collect_article_page_urls(self, driver, url: str) -> list[str]:
        return [url]

    def prepare_selenium_search_page(self, driver, keyword: str, wait_timeout: float) -> None:
        # Hook for dynamic search pages that need in-browser interactions/waits.
        return

    def build_search_urls(self, keyword: str) -> list[str]:
        query = quote_plus(keyword)
        if "{page}" in self.definition.search_url:
            return [
                self.definition.search_url.format(query=query, page=page)
                for page in range(1, self.config.max_pages + 1)
            ]
        return [self.definition.search_url.format(query=query)]

    def fetch_search_page(self, url: str) -> str:
        headers = {
            "User-Agent": self._user_agent(),
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

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        selectors = self.definition.search_result_selectors
        elements: Iterable
        if selectors:
            elements = []
            for selector in selectors:
                elements = list(elements) + soup.select(selector)
        else:
            elements = soup.select("a[href]")

        hits: list[SearchHit] = []
        for element in elements:
            href = element.get("href")
            if not href:
                continue
            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue
            title = element.get_text(strip=True) or None
            date_text = self._extract_date_text(element)
            published_at = parse_date(date_text) if date_text else None
            snippet = self._extract_snippet(element)
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

    def filter_hits_by_date(
        self,
        hits: list[SearchHit],
        cutoff_datetime: Optional[datetime] = None,
    ) -> list[SearchHit]:
        filtered: list[SearchHit] = []
        cutoff = cutoff_datetime.astimezone() if cutoff_datetime else self.config.resolve_search_cutoff()
        for hit in hits:
            if hit.published_at is None:
                filtered.append(hit)
                continue

            published_at = hit.published_at
            if published_at.tzinfo is None:
                published_at = published_at.replace(tzinfo=cutoff.tzinfo)

            # Search pages often expose only a date (no time); in that case we
            # keep the whole date if it is on/after the cutoff date.
            if self._is_date_only_timestamp(published_at):
                if published_at.date() >= cutoff.astimezone(published_at.tzinfo).date():
                    filtered.append(hit)
                continue

            if published_at.astimezone(cutoff.tzinfo) >= cutoff:
                filtered.append(hit)
        return filtered

    def detect_next_page(self, html: str, base_url: str) -> Optional[str]:
        soup = BeautifulSoup(html, "lxml")
        link = soup.find("a", attrs={"rel": "next"})
        if link and link.get("href"):
            return to_absolute_url(base_url, link.get("href"))
        for a in soup.select("a[href]"):
            text = (a.get_text() or "").strip().lower()
            if text in {"next", "suivant", "weiter", "seguinte", "suivante"}:
                return to_absolute_url(base_url, a.get("href"))
        return None

    def search(self, keyword: str, cutoff_datetime: Optional[datetime] = None) -> list[SearchHit]:
        hits: list[SearchHit] = []
        seen_urls: set[str] = set()
        urls = self.build_search_urls(keyword)
        pages_seen: set[str] = set()

        for url in urls:
            if url in pages_seen:
                continue
            pages_seen.add(url)
            html = self.fetch_search_page(url)
            page_hits = self.parse_search_results(html, url)
            page_hits = self.filter_hits_by_date(page_hits, cutoff_datetime=cutoff_datetime)
            new_hits = [hit for hit in page_hits if hit.url not in seen_urls]
            for hit in new_hits:
                seen_urls.add(hit.url)
            hits.extend(new_hits)

            if not new_hits:
                break
            if len(hits) >= self.config.max_results:
                break
            if "{page}" not in self.definition.search_url:
                if len(pages_seen) >= self.config.max_pages:
                    break
                next_url = self.detect_next_page(html, url)
                if not next_url or next_url in pages_seen:
                    break
                urls.append(next_url)
            time.sleep(self.config.rate_limit_seconds)
        return hits

    def _is_date_only_timestamp(self, value: datetime) -> bool:
        return (
            value.hour == 0
            and value.minute == 0
            and value.second == 0
            and value.microsecond == 0
        )

    def _is_allowed_url(self, url: str) -> bool:
        parsed = urlparse(url)
        if not parsed.netloc:
            return False
        if self.definition.domain not in parsed.netloc:
            return False
        for bad in self.definition.exclude_url_substrings:
            if bad in url:
                return False
        return True

    def _extract_date_text(self, element) -> Optional[str]:
        time_tag = element.find("time") if hasattr(element, "find") else None
        if time_tag:
            return time_tag.get("datetime") or time_tag.get_text(strip=True)
        parent = element.find_parent()
        if parent:
            time_tag = parent.find("time")
            if time_tag:
                return time_tag.get("datetime") or time_tag.get_text(strip=True)
            date_span = parent.find(class_=lambda c: c and "date" in c)
            if date_span:
                return date_span.get_text(strip=True)
        return None

    def _extract_snippet(self, element) -> Optional[str]:
        parent = element.find_parent()
        if not parent:
            return None
        paragraph = parent.find("p")
        if paragraph:
            return paragraph.get_text(strip=True)
        return None

    def _user_agent(self) -> str:
        if self.config.extra_user_agent:
            return self.config.extra_user_agent
        return (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/121.0 Safari/537.36"
        )
