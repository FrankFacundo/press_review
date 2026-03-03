from __future__ import annotations

from typing import Optional

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class ReporterMediaScraper(BaseMediaScraper):
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

const removeSelectors = [
  "#CybotCookiebotDialog",
  "#CybotCookiebotDialogBodyUnderlay",
  "#CybotCookiebotDialogNav",
  "#CybotCookiebotDialogBody",
  "#CybotCookiebotDialogBodyContent",
  "#CybotCookiebotDialogHeader",
  "#CybotCookiebotDialogFooter",
  "#CookiebotWidget",
  "[id^='CybotCookiebotDialog']",
  "[class*='CybotCookiebotDialog']",
  "[class*='CybotCookiebotScroll']",
  "[class*='CybotCookiebotFader']",
  "[id*='cookiebot'][role='dialog']",
  "[id*='cookiebot'][class*='overlay']",
  "[class*='cookiebot'][role='dialog']",
];

removeSelectors.forEach((selector) => {
  document.querySelectorAll(selector).forEach((el) => {
    hideElement(el);
    if (el.parentNode) {
      try {
        el.parentNode.removeChild(el);
      } catch (_) {
        // Best effort: hidden elements are sufficient for PDF output.
      }
    }
  });
});

const genericDialogs = document.querySelectorAll("[role='dialog'], [aria-modal='true'], dialog");
genericDialogs.forEach((el) => {
  const text = (el.innerText || "").toLowerCase();
  if (!text) return;
  const isCookieDialog =
    text.includes("cookies") &&
    (text.includes("alle zulassen") || text.includes("ablehnen") || text.includes("cookiebot"));
  if (isCookieDialog) {
    hideElement(el);
    if (el.parentNode) {
      try {
        el.parentNode.removeChild(el);
      } catch (_) {}
    }
  }
});

document.documentElement.classList.remove("CybotCookiebotDialogActive");
if (document.body) {
  document.body.style.setProperty("overflow", "visible", "important");
  document.body.style.setProperty("position", "static", "important");
}
"""
        try:
            driver.execute_script(script)
        except WebDriverException:
            return

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
