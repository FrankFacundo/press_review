from __future__ import annotations

from datetime import datetime
from typing import Optional

from bs4 import BeautifulSoup
from luxnews.browser_types import BrowserError

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
  el.style.setProperty("height", "0", "important");
  el.style.setProperty("overflow", "hidden", "important");
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
  ".cs-topbar",
  ".cs-header",
  ".cs-offcanvas",
  ".cs-search",
  ".cs-footer",
  "#secondary",
  ".cs-sidebar__area",
  ".cs-entry__post-related",
  ".cs-entry__subscribe",
  ".cs-entry__author",
  ".cs-entry__after-share-buttons",
  ".cs-entry__tags",
  ".cs-entry__metabar",
  ".cs-entry__share-buttons",
  ".pk-share-buttons-wrap",
  "[class*='mailmunch-forms']",
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

const content = document.querySelector("#content");
const primary = document.querySelector("#primary");
if (content && primary) {
  Array.from(content.children).forEach((child) => {
    if (child !== primary) {
      hideElement(child);
    }
  });
}

const printStyleId = "luxnews-siliconluxembourg-print-style";
let printStyle = document.getElementById(printStyleId);
if (!printStyle) {
  printStyle = document.createElement("style");
  printStyle.id = printStyleId;
  (document.head || document.documentElement).appendChild(printStyle);
}
printStyle.textContent = `
  body,
  main#main,
  .cs-site-content,
  .cs-container,
  #content,
  #primary,
  #primary .cs-entry__header,
  #primary .cs-entry__wrap,
  #primary .cs-entry__container,
  #primary .cs-entry__content-wrap,
  #primary .entry-content {
    background: #fff !important;
    background-color: #fff !important;
    background-image: none !important;
  }

  main#main,
  .cs-site-content,
  .cs-site-content .cs-container,
  #content,
  #primary {
    display: block !important;
    width: 100% !important;
    max-width: 920px !important;
    margin-left: auto !important;
    margin-right: auto !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
    float: none !important;
  }

  #primary .cs-entry__header,
  #primary .cs-entry__wrap,
  #primary .cs-entry__container,
  #primary .cs-entry__content-wrap,
  #primary .entry-content {
    width: 100% !important;
    max-width: 100% !important;
    margin-left: 0 !important;
    margin-right: 0 !important;
    padding-left: 0 !important;
    padding-right: 0 !important;
  }

  .cs-topbar,
  .cs-header,
  .cs-offcanvas,
  .cs-search,
  .cs-footer,
  #secondary,
  .cs-sidebar__area,
  .cs-entry__post-related,
  .cs-entry__subscribe,
  .cs-entry__author,
  .cs-entry__after-share-buttons,
  .cs-entry__tags,
  .cs-entry__metabar,
  .cs-entry__share-buttons,
  .pk-share-buttons-wrap,
  [class*="mailmunch-forms"],
  .cs-custom-content-header-after,
  .layout-ads,
  iframe[src*="doubleclick"],
  iframe[src*="googlesyndication"],
  [id*="google_ads_iframe"],
  [class*="ad-slot"],
  [id*="ad-slot"] {
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
