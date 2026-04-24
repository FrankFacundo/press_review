from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote_plus, urlparse

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class TageblattMediaScraper(BaseMediaScraper):
    SEARCH_ENTRY_URL = "https://www.tageblatt.lu/"
    RESULT_CARD_SELECTORS = [
        ".DocSearchModule article",
        ".DocSearchModule li",
        "article.StoryPreviewBox",
        ".SearchResult article",
        ".search-result article",
    ]
    DATE_PATTERN = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")
    NO_RESULTS_MARKERS = ("keine ergebnisse", "keine treffer", "nichts gefunden")

    def requires_selenium_search(self) -> bool:
        return True

    def build_search_urls(self, keyword: str) -> list[str]:
        # Tageblatt blocks direct query URLs in many contexts; start from home
        # and drive the website search UI instead.
        return [self.SEARCH_ENTRY_URL]

    def prepare_selenium_search_page(self, driver, keyword: str, wait_timeout: float) -> None:
        keyword_value = (keyword or "").strip()
        if not keyword_value:
            return

        self._open_sidebar_search_if_needed(driver)
        self._submit_quick_search(driver, keyword_value)
        self._ensure_on_search_page(driver, keyword_value)
        self._submit_doc_search_form(driver, keyword_value)
        self._wait_for_results(driver, wait_timeout)

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        cards = self._select_result_cards(soup)

        hits: list[SearchHit] = []
        seen_urls: set[str] = set()
        for card in cards:
            link = self._extract_result_link(card)
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
            if not self._is_probable_article_url(url):
                continue

            hits.append(
                SearchHit(
                    url=url,
                    title=self._extract_title(card, link),
                    published_at=self._parse_search_date(self._extract_date_text(card)),
                    snippet=self._extract_snippet(card),
                    media_id=self.definition.media_id,
                )
            )
            seen_urls.add(url)

        return hits

    def _select_result_cards(self, soup: BeautifulSoup) -> list:
        for selector in self.RESULT_CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                return cards
        return []

    def _extract_result_link(self, card):
        for selector in (
            "h1 a[href]",
            "h2 a[href]",
            "h3 a[href]",
            "a[href*='.html']",
            "a[href]",
        ):
            link = card.select_one(selector)
            if not link:
                continue
            href = (link.get("href") or "").strip()
            if not href:
                continue
            if selector == "a[href]" and not self._looks_like_article_href(href):
                continue
            return link
        return None

    def _extract_title(self, card, link) -> Optional[str]:
        for selector in (
            "h1.article-heading",
            "h2.article-heading",
            "h3.article-heading",
            "h1",
            "h2",
            "h3",
        ):
            heading = card.select_one(selector)
            if not heading:
                continue
            title = " ".join(heading.get_text(" ", strip=True).split())
            if title:
                return title

        title = " ".join((link.get_text(" ", strip=True) or "").split())
        return title or None

    def _extract_date_text(self, element) -> Optional[str]:
        if hasattr(element, "select_one"):
            time_node = element.select_one("time")
            if time_node:
                return time_node.get("datetime") or time_node.get_text(" ", strip=True)

            for selector in (
                ".article-meta",
                ".article-date",
                ".date",
                "[class*='date']",
                "[class*='meta']",
            ):
                node = element.select_one(selector)
                if not node:
                    continue
                value = " ".join(node.get_text(" ", strip=True).split())
                if value:
                    return value
        return super()._extract_date_text(element)

    def _extract_snippet(self, element) -> Optional[str]:
        if hasattr(element, "select_one"):
            snippet_node = element.select_one("p.article-teaser, .article-teaser, p")
            if snippet_node:
                snippet = " ".join(snippet_node.get_text(" ", strip=True).split())
                return snippet or None
        return super()._extract_snippet(element)

    def _parse_search_date(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None

        normalized = " ".join(raw.split())
        match = self.DATE_PATTERN.search(normalized)
        if match:
            day, month, year = (int(match.group(1)), int(match.group(2)), int(match.group(3)))
            try:
                return datetime(year, month, day, tzinfo=timezone.utc)
            except ValueError:
                return None

        return parse_date(normalized)

    def _looks_like_article_href(self, href: str) -> bool:
        path = urlparse(href).path.lower()
        if not path:
            return False
        if path.endswith(".html"):
            return True
        return "/nachrichten/" in path or "/luxemburg/" in path

    def _is_probable_article_url(self, url: str) -> bool:
        parsed = urlparse(url)
        path = parsed.path.lower()
        if not path or path == "/":
            return False
        if any(bad in path for bad in ("/nachrichten/suche", "/suche", "/search")):
            return False
        if path.endswith(".html"):
            return True
        return len([segment for segment in path.split("/") if segment]) >= 2

    def _open_sidebar_search_if_needed(self, driver) -> None:
        if self._has_visible_search_input(driver):
            return

        for selector in (".SideBarOpenIcon", ".BurgerMenuMobile", "#ChangeToggleMobile"):
            button = self._first_visible(driver, selector)
            if not button:
                continue
            try:
                button.click()
                time.sleep(0.4)
            except WebDriverException:
                continue
            if self._has_visible_search_input(driver):
                return

    def _submit_quick_search(self, driver, keyword: str) -> None:
        script = """
const keyword = arguments[0];
const modules = Array.from(document.querySelectorAll('.SearchModule'));
const visibleModule = modules.find((module) => {
  const input = module.querySelector('input.fi-search-box');
  if (!input) return false;
  const style = window.getComputedStyle(input);
  return style.display !== 'none' && style.visibility !== 'hidden' && input.offsetParent !== null;
});
const module = visibleModule || modules[0];
if (!module) return false;
const input = module.querySelector('input.fi-search-box');
if (!input) return false;
input.focus();
input.value = keyword;
input.dispatchEvent(new Event('input', { bubbles: true }));
input.dispatchEvent(new Event('change', { bubbles: true }));
const button = module.querySelector('button.IconLupe, button[type="button"], button');
if (button) {
  button.click();
  return true;
}
const enterEvent = new KeyboardEvent('keypress', {
  key: 'Enter',
  code: 'Enter',
  keyCode: 13,
  which: 13,
  bubbles: true,
});
input.dispatchEvent(enterEvent);
return true;
"""
        try:
            submitted = bool(driver.execute_script(script, keyword))
        except WebDriverException:
            submitted = False
        if submitted:
            time.sleep(0.8)

    def _submit_doc_search_form(self, driver, keyword: str) -> None:
        cutoff = self.config.resolve_search_cutoff().date()
        today = datetime.now().astimezone().date()
        begin_de = cutoff.strftime("%d.%m.%Y")
        end_de = today.strftime("%d.%m.%Y")
        begin_iso = cutoff.isoformat()
        end_iso = today.isoformat()

        script = """
const keyword = arguments[0];
const beginDe = arguments[1];
const endDe = arguments[2];
const beginIso = arguments[3];
const endIso = arguments[4];

const module = document.querySelector('.DocSearchModule');
if (!module) return false;

const setValue = (node, value) => {
  if (!node) return;
  node.focus();
  node.value = value;
  node.dispatchEvent(new Event('input', { bubbles: true }));
  node.dispatchEvent(new Event('change', { bubbles: true }));
};

const searchInput = module.querySelector('#SearchText');
setValue(searchInput, keyword);

const periodSpecific =
  module.querySelector('#PeriodSpecific') ||
  module.querySelector('input[name="Period"][value="specific"]');
if (periodSpecific) {
  periodSpecific.click();
  periodSpecific.dispatchEvent(new Event('change', { bubbles: true }));
}

setValue(module.querySelector('#DateFrom'), beginDe);
setValue(module.querySelector('#DateTo'), endDe);

const hiddenBegin = module.querySelector('input[name="strBeginDate"]');
const hiddenEnd = module.querySelector('input[name="strEndDate"]');
if (hiddenBegin && hiddenBegin.type === 'hidden') {
  hiddenBegin.value = beginIso;
}
if (hiddenEnd && hiddenEnd.type === 'hidden') {
  hiddenEnd.value = endIso;
}

const submit =
  module.querySelector('button[name="StartSearch"]') ||
  module.querySelector('input[name="StartSearch"]') ||
  module.querySelector('button[type="submit"]') ||
  module.querySelector('input[type="submit"]');
if (submit) {
  submit.click();
  return true;
}

if (searchInput) {
  const enterEvent = new KeyboardEvent('keypress', {
    key: 'Enter',
    code: 'Enter',
    keyCode: 13,
    which: 13,
    bubbles: true,
  });
  searchInput.dispatchEvent(enterEvent);
  return true;
}

return false;
"""
        try:
            submitted = bool(
                driver.execute_script(
                    script,
                    keyword,
                    begin_de,
                    end_de,
                    begin_iso,
                    end_iso,
                )
            )
        except WebDriverException:
            submitted = False
        if submitted:
            time.sleep(0.8)

    def _ensure_on_search_page(self, driver, keyword: str) -> None:
        """Navigate directly to the search URL if quick search did not reach the results page."""
        current_url = driver.current_url.lower()
        if "/nachrichten/suche" in current_url:
            state = self._read_search_state(driver)
            if not state.get("http_error"):
                return

        encoded_keyword = quote_plus(keyword)
        try:
            driver.get(f"https://www.tageblatt.lu/Nachrichten/Suche?search={encoded_keyword}")
            time.sleep(0.8)
        except WebDriverException:
            return

    def _wait_for_results(self, driver, wait_timeout: float) -> None:
        deadline = time.time() + max(wait_timeout, 8.0)
        while time.time() < deadline:
            state = self._read_search_state(driver)
            if state.get("http_error"):
                return
            if state.get("has_results"):
                return
            if state.get("no_results"):
                return
            time.sleep(0.25)

    def _read_search_state(self, driver) -> dict:
        script = """
const bodyText = ((document.body && document.body.innerText) || '').toLowerCase();
const noResultsMarkers = ['keine ergebnisse', 'keine treffer', 'nichts gefunden'];
const noResults = noResultsMarkers.some((token) => bodyText.includes(token))
  || /suchergebnisse\\s*\\(\\s*0\\s*\\)/.test(bodyText);
const hasResults =
  document.querySelectorAll(
    '.DocSearchModule article, .DocSearchModule li, article.StoryPreviewBox, .SearchResult article, .search-result article'
  ).length > 0
  || /suchergebnisse\\s*\\(\\s*[1-9]/.test(bodyText);
const httpError = bodyText.includes('http error 400');
return {
  no_results: noResults,
  has_results: hasResults,
  http_error: httpError,
};
"""
        try:
            result = driver.execute_script(script)
        except WebDriverException:
            return {"no_results": False, "has_results": False, "http_error": False}
        if not isinstance(result, dict):
            return {"no_results": False, "has_results": False, "http_error": False}
        return result

    def _has_visible_search_input(self, driver) -> bool:
        return self._first_visible(driver, "input.fi-search-box") is not None

    def _first_visible(self, driver, selector: str):
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except WebDriverException:
            return None
        for element in elements:
            try:
                if element.is_displayed():
                    return element
            except WebDriverException:
                continue
        return None
