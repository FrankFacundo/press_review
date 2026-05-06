from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Iterator, Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from luxnews.browser_types import BrowserError

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class LessentielMediaScraper(BaseMediaScraper):
    LUXEMBOURG_URL = "https://www.lessentiel.lu/fr/luxembourg"

    def requires_browser_search(self) -> bool:
        # The Luxembourg listing is the source for discovery; browser loading keeps
        # the rendered Next.js page behavior aligned with normal runs.
        return True

    def build_search_urls(self, keyword: str) -> list[str]:
        # L'Essentiel's search bar is not working properly: it can miss articles
        # whose body contains the searched keyword, for example "BNP Paribas".
        # Scan the Luxembourg listing and validate keywords inside each article.
        return [self.LUXEMBOURG_URL]

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        payload = self._extract_next_data_payload(html)
        requested_query = self._extract_requested_query(base_url)
        payload_query = self._extract_payload_query(payload)
        teasers = self._extract_payload_teasers(payload)

        if self._is_payload_query_usable(requested_query, payload_query):
            hits = self._build_hits_from_teasers(teasers, base_url)
            if hits:
                return hits

        return self._parse_hits_from_dom(html, base_url)

    def prepare_browser_search_page(self, driver, keyword: str, wait_timeout: float) -> None:
        self._wait_for_story_links(driver, wait_timeout)

    def _build_hits_from_teasers(self, teasers: list[dict], base_url: str) -> list[SearchHit]:
        hits: list[SearchHit] = []
        seen_urls: set[str] = set()
        for teaser in teasers:
            if not isinstance(teaser, dict):
                continue

            href = teaser.get("url")
            if not isinstance(href, str) or not href.strip():
                continue

            url = to_absolute_url(base_url, href)
            if "/story/" not in url:
                continue
            if url in seen_urls:
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
            seen_urls.add(url)
        return hits

    def _parse_hits_from_dom(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        hits: list[SearchHit] = []
        seen_urls: set[str] = set()

        for anchor in soup.select("a[href*='/story/']"):
            href = anchor.get("href")
            if not isinstance(href, str) or not href.strip():
                continue

            url = to_absolute_url(base_url, href)
            if url in seen_urls:
                continue
            if not self._is_allowed_url(url):
                continue

            container = anchor.find_parent(["article", "li", "section", "div"]) or anchor
            title = self._extract_dom_title(anchor, container)
            date_text = self._extract_dom_date_text(anchor, container)
            published_at = parse_date(date_text) if date_text else None
            snippet = self._extract_dom_snippet(container)

            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    published_at=published_at,
                    snippet=snippet,
                    media_id=self.definition.media_id,
                )
            )
            seen_urls.add(url)

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

    def _extract_payload_teasers(self, payload: dict) -> list[dict]:
        page_data = (
            payload.get("props", {})
            .get("pageProps", {})
            .get("store", {})
            .get("pageData", {})
            .get("data", {})
            if isinstance(payload, dict)
            else {}
        )
        if not isinstance(page_data, dict):
            return []
        return list(self._iter_teaser_dicts(page_data))

    def _iter_teaser_dicts(self, value) -> Iterator[dict]:
        if isinstance(value, dict):
            href = value.get("url")
            if isinstance(href, str) and "/story/" in href:
                yield value
            for child in value.values():
                yield from self._iter_teaser_dicts(child)
            return

        if isinstance(value, list):
            for child in value:
                yield from self._iter_teaser_dicts(child)

    def _extract_requested_query(self, base_url: str) -> Optional[str]:
        parsed = urlparse(base_url)
        query = parse_qs(parsed.query).get("q", [None])[0]
        if not isinstance(query, str):
            return None
        query = query.strip()
        return query or None

    def _extract_payload_query(self, payload: dict) -> Optional[str]:
        query = payload.get("query", {}).get("q") if isinstance(payload, dict) else None
        if not isinstance(query, str):
            return None
        query = query.strip()
        return query or None

    def _is_payload_query_usable(
        self,
        requested_query: Optional[str],
        payload_query: Optional[str],
    ) -> bool:
        if not requested_query or not payload_query:
            return True
        return requested_query.casefold() == payload_query.casefold()

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

    def _extract_dom_title(self, anchor, container) -> Optional[str]:
        labelled = anchor.get("aria-label")
        if isinstance(labelled, str):
            cleaned = " ".join(labelled.split())
            if cleaned:
                return cleaned

        for node in container.select("h1, h2, h3, h4"):
            text = " ".join(node.get_text(" ", strip=True).split())
            if text:
                return text

        raw = " ".join(anchor.get_text(" ", strip=True).split())
        return raw or None

    def _extract_dom_date_text(self, anchor, container) -> Optional[str]:
        for scope in (anchor, container):
            time_tag = scope.find("time") if hasattr(scope, "find") else None
            if not time_tag:
                continue
            value = time_tag.get("datetime") or time_tag.get_text(strip=True)
            if value:
                return value
        return None

    def _extract_dom_snippet(self, container) -> Optional[str]:
        paragraph = container.find("p") if hasattr(container, "find") else None
        if not paragraph:
            return None
        snippet = " ".join(paragraph.get_text(" ", strip=True).split())
        return snippet or None

    def _wait_for_story_links(self, driver, wait_timeout: float) -> None:
        start = time.time()
        deadline = start + max(wait_timeout, 8.0)
        while time.time() < deadline:
            state = self._read_listing_state(driver)
            if state.get("story_links", 0) > 0:
                return
            if state.get("login_gate") and time.time() - start > 2.0:
                return
            time.sleep(0.25)

    def _read_listing_state(self, driver) -> dict:
        script = """
const bodyText = ((document.body && document.body.innerText) || '').toLowerCase();
const loginGate =
  (bodyText.includes('inscris') && bodyText.includes('recherche')) ||
  (bodyText.includes('deja enregistre') && bodyText.includes('login'));
const storyLinks = document.querySelectorAll('a[href*="/story/"]').length;
return { login_gate: loginGate, story_links: storyLinks };
"""
        try:
            result = driver.execute_script(script)
        except BrowserError:
            return {"login_gate": False, "story_links": 0}
        return result if isinstance(result, dict) else {"login_gate": False, "story_links": 0}
