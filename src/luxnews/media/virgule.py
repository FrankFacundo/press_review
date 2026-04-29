from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from luxnews.browser_types import BrowserError
from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class VirguleMediaScraper(BaseMediaScraper):
    RESULT_LINK_SELECTOR = "article a[class*='default-teaser__link']"
    DATE_PATTERN = re.compile(r"\b(\d{1,2})[./](\d{1,2})[./](\d{4})\b")

    def requires_browser_search(self) -> bool:
        return True

    def prepare_article_for_pdf(self, driver) -> None:
        script = """
const hideElement = (el) => {
  if (!el) return;
  el.style.setProperty("display", "none", "important");
  el.style.setProperty("visibility", "hidden", "important");
  el.style.setProperty("opacity", "0", "important");
  el.style.setProperty("height", "0", "important");
  el.style.setProperty("overflow", "hidden", "important");
  el.setAttribute("aria-hidden", "true");
};

const removeSelectors = [
  "#ad_wallpaper-t1",
  "#leaderboard-observe-target",
  "[id^='ad_']",
  "[id*='google_ads_iframe']",
  "[class*='page-layout_takeoverAdContainer']",
  "[class*='page-layout_leadingAdContainer']",
  "[class*='takeover-ad-wallpaper']",
  "[class*='takeoverAdWallpaper']",
  "[class*='takeover-ad-leaderboard']",
  "[class*='takeoverAdLeaderboard']",
  "[class*='ad-element_ad']",
  "[class*='ad--wallpaper']",
  "[class*='ad--leaderboard']",
  "iframe[src*='doubleclick']",
  "iframe[src*='googlesyndication']",
];

removeSelectors.forEach((selector) => {
  document.querySelectorAll(selector).forEach(hideElement);
});

const printStyleId = "luxnews-virgule-print-style";
let printStyle = document.getElementById(printStyleId);
if (!printStyle) {
  printStyle = document.createElement("style");
  printStyle.id = printStyleId;
  (document.head || document.documentElement).appendChild(printStyle);
}
printStyle.textContent = `
  html,
  body,
  #__next,
  [class*="page-layout_pageLayout"],
  [class*="page-layout_contentContainer"],
  [class*="takeover-ad-content-container"],
  [class*="article-ads-wrapper_adsWrapper"],
  [class*="article-two-thirds-layout_articleTwoThirdsLayout"],
  [class*="article-two-thirds-layout_article"] {
    background: #fff !important;
    background-color: #fff !important;
    background-image: none !important;
  }

  [class*="page-layout_takeoverAdContainer"],
  [class*="page-layout_leadingAdContainer"],
  [class*="takeover-ad-wallpaper"],
  [class*="takeoverAdWallpaper"],
  [class*="takeover-ad-leaderboard"],
  [class*="takeoverAdLeaderboard"],
  [class*="ad-element_ad"],
  [id^="ad_"],
  [id*="google_ads_iframe"],
  iframe[src*="doubleclick"],
  iframe[src*="googlesyndication"] {
    display: none !important;
    visibility: hidden !important;
    opacity: 0 !important;
    height: 0 !important;
    overflow: hidden !important;
  }
`;
"""
        try:
            driver.execute_script(script)
        except BrowserError:
            return

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        links = soup.select(self.RESULT_LINK_SELECTOR)

        hits: list[SearchHit] = []
        for link in links:
            href = link.get("href")
            if not isinstance(href, str) or not href.strip():
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            hits.append(
                SearchHit(
                    url=url,
                    title=self._extract_title(link),
                    published_at=self._extract_published_at(link),
                    snippet=self._extract_snippet(link),
                    media_id=self.definition.media_id,
                )
            )
        return hits

    def _extract_title(self, link) -> Optional[str]:
        title_node = link.select_one("span[class*='teaser-content__title']")
        if title_node:
            title = " ".join(title_node.get_text(" ", strip=True).split())
            if title:
                return title

        spans = link.select("span")
        if len(spans) >= 2:
            fallback_title = " ".join(spans[1].get_text(" ", strip=True).split())
            if fallback_title:
                return fallback_title

        return None

    def _extract_snippet(self, link) -> Optional[str]:
        snippet_node = link.select_one("p[class*='teaser-content__introduction']")
        if not snippet_node:
            return None
        snippet = " ".join(snippet_node.get_text(" ", strip=True).split())
        return snippet or None

    def _extract_published_at(self, link) -> Optional[datetime]:
        time_node = link.select_one("time")
        if not time_node:
            return None

        candidates = [
            (time_node.get("datetime") or "").strip(),
            " ".join(time_node.get_text(" ", strip=True).split()),
        ]
        for raw in candidates:
            parsed = self._parse_teaser_date(raw)
            if parsed:
                return parsed
        return None

    def _parse_teaser_date(self, raw: str) -> Optional[datetime]:
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
