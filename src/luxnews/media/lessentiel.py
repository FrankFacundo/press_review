from __future__ import annotations

import json
import time
from datetime import datetime
from typing import Optional
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class LessentielMediaScraper(BaseMediaScraper):
    def requires_selenium_search(self) -> bool:
        # Search results are rendered by client-side state and require a logged-in session.
        return True

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        payload = self._extract_next_data_payload(html)
        requested_query = self._extract_requested_query(base_url)
        payload_query = self._extract_payload_query(payload)
        teasers = (
            payload.get("props", {})
            .get("pageProps", {})
            .get("store", {})
            .get("pageData", {})
            .get("data", {})
            .get("teasers", [])
        )

        if self._is_payload_query_usable(requested_query, payload_query) and isinstance(teasers, list):
            hits = self._build_hits_from_teasers(teasers, base_url)
            if hits:
                return hits

        return self._parse_hits_from_dom(html, base_url)

    def prepare_selenium_search_page(self, driver, keyword: str, wait_timeout: float) -> None:
        self._sync_search_input_with_keyword(driver, keyword)
        self._wait_for_search_results(driver, wait_timeout)

    def _build_hits_from_teasers(self, teasers: list[dict], base_url: str) -> list[SearchHit]:
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

    def _sync_search_input_with_keyword(self, driver, keyword: str) -> None:
        keyword_value = (keyword or "").strip()
        if not keyword_value:
            return

        search_input = None
        deadline = time.time() + 5.0
        while time.time() < deadline:
            try:
                candidate = driver.find_element(By.CSS_SELECTOR, "input#search")
            except WebDriverException:
                candidate = None
            if candidate is not None:
                search_input = candidate
                break
            time.sleep(0.2)
        if search_input is None:
            return

        try:
            current_value = (search_input.get_attribute("value") or "").strip()
        except WebDriverException:
            current_value = ""
        if current_value.casefold() == keyword_value.casefold():
            return

        try:
            search_input.click()
        except WebDriverException:
            pass

        try:
            search_input.clear()
        except WebDriverException:
            pass

        try:
            search_input.send_keys(Keys.CONTROL, "a")
            search_input.send_keys(Keys.BACKSPACE)
            search_input.send_keys(keyword_value)
            search_input.send_keys(Keys.ENTER)
        except WebDriverException:
            return

    def _wait_for_search_results(self, driver, wait_timeout: float) -> None:
        start = time.time()
        deadline = start + max(wait_timeout, 8.0)
        while time.time() < deadline:
            state = self._read_search_state(driver)
            if state.get("story_links", 0) > 0:
                return
            if state.get("no_results"):
                return
            if state.get("login_gate") and time.time() - start > 2.0:
                return
            time.sleep(0.25)

    def _read_search_state(self, driver) -> dict:
        script = """
const bodyText = ((document.body && document.body.innerText) || '').toLowerCase();
const loginGate =
  (bodyText.includes('inscris') && bodyText.includes('recherche')) ||
  (bodyText.includes('deja enregistre') && bodyText.includes('login'));
const noResults = bodyText.includes('aucun résultat') || bodyText.includes('aucun resultat');
const storyLinks = document.querySelectorAll('a[href*="/story/"]').length;
return { login_gate: loginGate, no_results: noResults, story_links: storyLinks };
"""
        try:
            result = driver.execute_script(script)
        except WebDriverException:
            return {"login_gate": False, "no_results": False, "story_links": 0}
        return result if isinstance(result, dict) else {"login_gate": False, "no_results": False, "story_links": 0}
