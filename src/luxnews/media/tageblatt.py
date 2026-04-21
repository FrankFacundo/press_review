from __future__ import annotations

import gzip
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

from bs4 import BeautifulSoup
import requests
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import matches_keyword_with_exclusions, normalize_text, parse_date, to_absolute_url


class TageblattMediaScraper(BaseMediaScraper):
    SEARCH_ENTRY_URL = "https://www.tageblatt.lu/"
    SITEMAP_INDEX_URL = "https://www.tageblatt.lu/Sitemap_Index.xml.gz"
    SITEMAP_CURRENT_URL = "https://www.tageblatt.lu/Sitemap_Current.xml.gz"
    SITEMAP_NAMESPACE = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    ARCHIVE_SITEMAP_PATTERN = re.compile(r"Sitemap_Archiv_(\d{4})_(\d{1,2})\.xml\.gz$")
    ARTICLE_ID_SUFFIX_PATTERN = re.compile(r"-\d+\.html?$", re.IGNORECASE)
    RESULT_CARD_SELECTORS = [
        ".DocSearchModule article",
        ".DocSearchModule li",
        "article.StoryPreviewBox",
        ".SearchResult article",
        ".search-result article",
    ]
    DATE_PATTERN = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")
    NO_RESULTS_MARKERS = ("keine ergebnisse", "keine treffer", "nichts gefunden")

    def __init__(self, definition, config) -> None:
        super().__init__(definition, config)
        self._article_html_cache: dict[str, Optional[str]] = {}

    def requires_selenium_search(self) -> bool:
        return False

    def prefers_plain_search(self) -> bool:
        # Tageblatt's /Nachrichten/Suche endpoint returns HTTP 400 and is
        # disallowed by robots.txt, so only the sitemap path is usable —
        # regardless of search_use_selenium / headless / debug toggles.
        return True

    def build_search_urls(self, keyword: str) -> list[str]:
        return [self.SITEMAP_CURRENT_URL]

    SEARCH_FETCH_WORKERS = 8

    def search(self, keyword: str, cutoff_datetime: Optional[datetime] = None) -> list[SearchHit]:
        keyword_value = (keyword or "").strip()
        if not keyword_value:
            return []

        cutoff = cutoff_datetime.astimezone() if cutoff_datetime else self.config.resolve_search_cutoff()

        candidates: list[tuple[str, Optional[datetime]]] = []
        seen_urls: set[str] = set()
        for url, published_at in self._iter_sitemap_article_candidates(cutoff):
            if url in seen_urls:
                continue
            if not self._is_allowed_url(url):
                continue
            if not self._is_probable_article_url(url):
                continue
            seen_urls.add(url)
            candidates.append((url, published_at))

        if not candidates:
            return []

        # Fast path: keep candidates whose URL slug already matches the
        # keyword — they do not need an HTTP fetch to confirm the hit.
        slug_matches: list[tuple[str, Optional[datetime]]] = []
        body_check: list[tuple[str, Optional[datetime]]] = []
        for url, published_at in candidates:
            if self._slug_matches_keyword(url, keyword_value):
                slug_matches.append((url, published_at))
            else:
                body_check.append((url, published_at))

        def fetch(url: str) -> Optional[str]:
            try:
                return self.fetch_search_page(url)
            except RuntimeError:
                return None

        all_urls = [url for url, _ in slug_matches] + [url for url, _ in body_check]
        missing = [url for url in all_urls if url not in self._article_html_cache]
        if missing:
            workers = max(1, min(self.SEARCH_FETCH_WORKERS, len(missing)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                for url, html in zip(missing, pool.map(fetch, missing)):
                    self._article_html_cache[url] = html
        fetched = {url: self._article_html_cache.get(url) for url in all_urls}

        hits: list[SearchHit] = []
        for url, published_at in candidates:
            html = fetched.get(url)
            slug_hit = (url, published_at) in slug_matches
            title: Optional[str] = self._slug_to_title(url)
            snippet: Optional[str] = None

            if html is not None:
                article_soup = BeautifulSoup(html, "lxml")
                extracted_title = self._extract_article_title(article_soup)
                if extracted_title:
                    title = extracted_title
                snippet = self._extract_article_snippet(article_soup)
                if not slug_hit and not self._article_matches_keyword(article_soup, keyword_value):
                    continue
            elif not slug_hit:
                # No HTML and no slug hit -> cannot confirm a match.
                continue

            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    published_at=published_at,
                    snippet=snippet,
                    media_id=self.definition.media_id,
                )
            )
            if len(hits) >= self.config.max_results:
                break

        return hits

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
        search_input = self._first_visible(driver, "input.fi-search-box")
        if search_input is None:
            return

        button = self._first_visible(
            driver,
            ".SearchModule button.IconLupe, .SearchModule button[type='button'], .SearchModule button",
        )

        try:
            search_input.click()
        except WebDriverException:
            pass

        try:
            search_input.clear()
        except WebDriverException:
            pass

        submitted = self._type_keyword(search_input, keyword)
        if button is not None:
            try:
                button.click()
                submitted = True
            except WebDriverException:
                pass

        if not submitted:
            try:
                search_input.send_keys(Keys.ENTER)
                submitted = True
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
        if self._wait_for_search_page(driver, timeout_seconds=1.5):
            return

        for _ in range(2):
            self._open_sidebar_search_if_needed(driver)
            self._submit_quick_search(driver, keyword)
            if self._wait_for_search_page(driver, timeout_seconds=3.0):
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

    def _wait_for_search_page(self, driver, timeout_seconds: float) -> bool:
        deadline = time.time() + max(timeout_seconds, 0.25)
        while time.time() < deadline:
            state = self._read_search_state(driver)
            if state.get("on_search_page") and not state.get("http_error"):
                return True
            time.sleep(0.25)
        return False

    def _read_search_state(self, driver) -> dict:
        script = """
const bodyText = ((document.body && document.body.innerText) || '').toLowerCase();
const url = (window.location && window.location.href || '').toLowerCase();
const noResultsMarkers = ['keine ergebnisse', 'keine treffer', 'nichts gefunden'];
const noResults = noResultsMarkers.some((token) => bodyText.includes(token))
  || /suchergebnisse\\s*\\(\\s*0\\s*\\)/.test(bodyText);
const hasResults =
  document.querySelectorAll(
    '.DocSearchModule article, .DocSearchModule li, article.StoryPreviewBox, .SearchResult article, .search-result article'
  ).length > 0
  || /suchergebnisse\\s*\\(\\s*[1-9]/.test(bodyText);
const httpError = bodyText.includes('http error 400');
const onSearchPage = url.includes('/nachrichten/suche') || document.querySelector('.DocSearchModule') !== null;
return {
  no_results: noResults,
  has_results: hasResults,
  http_error: httpError,
  on_search_page: onSearchPage,
};
"""
        try:
            result = driver.execute_script(script)
        except WebDriverException:
            return {
                "no_results": False,
                "has_results": False,
                "http_error": False,
                "on_search_page": False,
            }
        if not isinstance(result, dict):
            return {
                "no_results": False,
                "has_results": False,
                "http_error": False,
                "on_search_page": False,
            }
        return result

    def _has_visible_search_input(self, driver) -> bool:
        return self._first_visible(driver, "input.fi-search-box") is not None

    def _type_keyword(self, search_input, keyword: str) -> bool:
        typed = False
        for modifier in (Keys.COMMAND, Keys.CONTROL):
            try:
                search_input.send_keys(modifier, "a")
                search_input.send_keys(Keys.BACKSPACE)
                search_input.send_keys(keyword)
                return True
            except WebDriverException:
                continue
        try:
            search_input.clear()
        except WebDriverException:
            pass
        try:
            search_input.send_keys(keyword)
            typed = True
        except WebDriverException:
            typed = False
        return typed

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

    def _iter_sitemap_article_candidates(
        self,
        cutoff_datetime: datetime,
    ) -> list[tuple[str, Optional[datetime]]]:
        now = datetime.now().astimezone()
        sitemap_urls = self._select_sitemap_urls(cutoff_datetime=cutoff_datetime, now=now)

        candidates: list[tuple[str, Optional[datetime]]] = []
        for sitemap_url in sitemap_urls:
            candidates.extend(
                self._parse_sitemap_urls(
                    sitemap_url=sitemap_url,
                    cutoff_datetime=cutoff_datetime,
                )
            )

        candidates.sort(key=lambda item: item[1] or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        return candidates

    def _select_sitemap_urls(
        self,
        cutoff_datetime: datetime,
        now: datetime,
    ) -> list[str]:
        sitemap_urls = [self.SITEMAP_CURRENT_URL]
        cutoff_key = (cutoff_datetime.year, cutoff_datetime.month)
        now_key = (now.year, now.month)
        if cutoff_key == now_key:
            return sitemap_urls

        try:
            index_xml = self._fetch_sitemap_xml(self.SITEMAP_INDEX_URL)
        except RuntimeError:
            return sitemap_urls

        month_keys = set(self._iter_month_keys(cutoff_datetime, now))
        root = ET.fromstring(index_xml.lstrip("\ufeff"))
        for loc_node in root.findall("sm:sitemap/sm:loc", self.SITEMAP_NAMESPACE):
            loc = (loc_node.text or "").strip()
            if not loc:
                continue
            match = self.ARCHIVE_SITEMAP_PATTERN.search(loc)
            if not match:
                continue
            month_key = (int(match.group(1)), int(match.group(2)))
            if month_key in month_keys:
                sitemap_urls.append(loc)
        return sitemap_urls

    def _parse_sitemap_urls(
        self,
        sitemap_url: str,
        cutoff_datetime: datetime,
    ) -> list[tuple[str, Optional[datetime]]]:
        xml_text = self._fetch_sitemap_xml(sitemap_url)
        root = ET.fromstring(xml_text.lstrip("\ufeff"))

        candidates: list[tuple[str, Optional[datetime]]] = []
        for url_node in root.findall("sm:url", self.SITEMAP_NAMESPACE):
            loc_text = url_node.findtext("sm:loc", default="", namespaces=self.SITEMAP_NAMESPACE).strip()
            if not loc_text:
                continue

            lastmod_text = url_node.findtext(
                "sm:lastmod",
                default="",
                namespaces=self.SITEMAP_NAMESPACE,
            ).strip()
            published_at = parse_date(lastmod_text) if lastmod_text else None
            if published_at and published_at.astimezone(cutoff_datetime.tzinfo) < cutoff_datetime:
                continue
            candidates.append((loc_text, published_at))
        return candidates

    def _fetch_sitemap_xml(self, sitemap_url: str) -> str:
        headers = {"User-Agent": self._user_agent()}
        try:
            response = requests.get(sitemap_url, headers=headers, timeout=self.config.request_timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(f"Failed to fetch Tageblatt sitemap: {sitemap_url}") from exc

        raw_content = response.content
        if sitemap_url.endswith(".gz"):
            raw_content = gzip.decompress(raw_content)
        return raw_content.decode("utf-8", errors="replace")

    def _iter_month_keys(self, start: datetime, end: datetime) -> list[tuple[int, int]]:
        month_keys: list[tuple[int, int]] = []
        year = start.year
        month = start.month
        while (year, month) <= (end.year, end.month):
            month_keys.append((year, month))
            month += 1
            if month > 12:
                month = 1
                year += 1
        return month_keys

    def _slug_matches_keyword(self, url: str, keyword: str) -> bool:
        slug_text = self._slug_to_title(url)
        if not slug_text:
            return False
        return matches_keyword_with_exclusions(normalize_text(slug_text), keyword)

    def _slug_to_title(self, url: str) -> Optional[str]:
        path = urlparse(url).path
        if not path:
            return None
        last_segment = path.rstrip("/").rsplit("/", 1)[-1]
        if not last_segment:
            return None
        last_segment = self.ARTICLE_ID_SUFFIX_PATTERN.sub("", last_segment)
        last_segment = re.sub(r"\.html?$", "", last_segment, flags=re.IGNORECASE)
        cleaned = last_segment.replace("-", " ").replace("_", " ").strip()
        return cleaned or None

    def _article_matches_keyword(self, soup: BeautifulSoup, keyword: str) -> bool:
        text_parts: list[str] = []
        title = self._extract_article_title(soup)
        if title:
            text_parts.append(title)

        article = soup.select_one("main article") or soup.select_one("article") or soup.body
        if article is not None:
            text_parts.append(article.get_text(" ", strip=True))

        normalized_text = normalize_text(" ".join(text_parts))
        return matches_keyword_with_exclusions(normalized_text, keyword)

    def _extract_article_title(self, soup: BeautifulSoup) -> Optional[str]:
        for selector in ("h1", "meta[property='og:title']", "title"):
            node = soup.select_one(selector)
            if not node:
                continue
            if node.name == "meta":
                title = (node.get("content") or "").strip()
            else:
                title = " ".join(node.get_text(" ", strip=True).split())
            if title:
                return title
        return None

    def _extract_article_snippet(self, soup: BeautifulSoup) -> Optional[str]:
        for selector in ("meta[name='description']", "meta[property='og:description']", "main article p", "article p"):
            node = soup.select_one(selector)
            if not node:
                continue
            if node.name == "meta":
                snippet = (node.get("content") or "").strip()
            else:
                snippet = " ".join(node.get_text(" ", strip=True).split())
            if snippet:
                return snippet
        return None
