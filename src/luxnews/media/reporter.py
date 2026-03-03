from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class ReporterMediaScraper(BaseMediaScraper):
    def prefers_plain_search(self) -> bool:
        return True

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        articles = soup.select("article.post-card-wrap")
        hits: list[SearchHit] = []

        for article in articles:
            # Find the title link (the one with text content)
            link = None
            for a in article.select("a[href]"):
                if a.get_text(strip=True):
                    link = a
                    break
            if not link:
                continue

            href = link.get("href")
            if not href:
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            title = link.get_text(strip=True) or None
            published_at = None
            time_tag = article.select_one("time[datetime]")
            if time_tag:
                raw = time_tag.get("datetime") or time_tag.get_text(strip=True)
                published_at = parse_date(raw) if raw else None

            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    published_at=published_at,
                    snippet=None,
                    media_id=self.definition.media_id,
                )
            )

        return hits
