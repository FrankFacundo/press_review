from __future__ import annotations

from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class SiliconLuxembourgMediaScraper(BaseMediaScraper):
    def prefers_plain_search(self) -> bool:
        return True

    def prepare_article_for_pdf(self, driver) -> None:
        script = """
const hideElement = (el) => {
  if (!el) return;
  el.style.setProperty("display", "none", "important");
  el.style.setProperty("visibility", "hidden", "important");
  el.style.setProperty("opacity", "0", "important");
  el.setAttribute("aria-hidden", "true");
};

const removeElement = (el) => {
  if (!el) return;
  hideElement(el);
  if (!el.parentNode) return;
  try {
    el.parentNode.removeChild(el);
  } catch (_) {
    // Best effort: hidden state is already enough for PDF output.
  }
};

const removeSelectors = [
  // Main top billboard ad block shown above article content.
  ".cs-custom-content-header-after",
  ".layout-ads",
  "a[aria-label='banner-billboard']",
  "img[alt='banner-billboard']",
  // Common injected ad iframes/slots used by the site template.
  "iframe[src*='doubleclick']",
  "iframe[src*='googlesyndication']",
  "[id*='google_ads_iframe']",
  "[class*='ad-slot']",
  "[id*='ad-slot']",
];

removeSelectors.forEach((selector) => {
  document.querySelectorAll(selector).forEach(removeElement);
});
"""
        try:
            driver.execute_script(script)
        except WebDriverException:
            return

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        articles = soup.select("article.cs-entry")
        hits: list[SearchHit] = []

        for article in articles:
            title_link = article.select_one(".cs-entry__title a[href]")
            if not title_link:
                continue

            href = title_link.get("href")
            if not href:
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            title = title_link.get_text(strip=True) or None
            published_at = self._parse_meta_date(article)
            if published_at is None:
                continue

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

    def _parse_meta_date(self, article) -> Optional[datetime]:
        date_div = article.select_one(".cs-meta-date")
        if not date_div:
            return None
        raw = date_div.get_text(strip=True)
        if not raw:
            return None
        parsed = parse_date(raw)
        if parsed:
            return parsed
        return None
