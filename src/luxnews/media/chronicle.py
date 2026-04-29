from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from luxnews.browser_types import BrowserError

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url

# Image URLs contain dates in two formats:
#   New: /images/2026/Mar/20260302_...
#   Old: /images/KA//20160129_...
_IMG_DATE_RE = re.compile(r"/images/.*?(\d{4})(\d{2})(\d{2})[_-]")


class ChronicleMediaScraper(BaseMediaScraper):
    NEWS_URL = "https://www.chronicle.lu/news"
    MAX_NEWS_PAGES = 25

    def __init__(self, definition, config) -> None:
        super().__init__(definition, config)
        self._recent_hits_cache: dict[str, list[SearchHit]] = {}

    def prefers_plain_search(self) -> bool:
        return True

    def build_search_urls(self, keyword: str) -> list[str]:
        return [self.NEWS_URL]

    def search(self, keyword: str, cutoff_datetime: Optional[datetime] = None) -> list[SearchHit]:
        cutoff = cutoff_datetime.astimezone() if cutoff_datetime else self.config.resolve_search_cutoff()
        cache_key = cutoff.isoformat()
        cached_hits = self._recent_hits_cache.get(cache_key)
        if cached_hits is not None:
            return list(cached_hits)

        hits: list[SearchHit] = []
        seen_urls: set[str] = set()
        for page_url in self._build_news_page_urls():
            html = self.fetch_search_page(page_url)
            page_hits = self.parse_search_results(html, page_url)
            filtered_hits = self.filter_hits_by_date(page_hits, cutoff_datetime=cutoff)

            for hit in filtered_hits:
                if hit.url in seen_urls:
                    continue
                seen_urls.add(hit.url)
                hits.append(hit)

            if len(hits) >= self.config.max_results:
                break
            if self._page_reached_cutoff(page_hits, cutoff):
                break
            time.sleep(self.config.rate_limit_seconds)

        self._recent_hits_cache[cache_key] = list(hits)
        return list(hits)

    def prepare_article_for_pdf(self, driver) -> None:
        script = """
const hideElement = (el) => {
  if (!el) return;
  el.style.setProperty('display', 'none', 'important');
  el.style.setProperty('visibility', 'hidden', 'important');
  el.style.setProperty('height', '0', 'important');
  el.style.setProperty('overflow', 'hidden', 'important');
};

const printStyleId = 'luxnews-chronicle-print-style';
let printStyle = document.getElementById(printStyleId);
if (!printStyle) {
  printStyle = document.createElement('style');
  printStyle.id = printStyleId;
  document.head.appendChild(printStyle);
}
printStyle.textContent = `
  @page { margin: 42px 24px 24px 24px; }
  body { margin: 0 !important; }
`;

[
  'header#header',
  'nav.navbar',
  '.main-nav-wrap',
  '.sidebar.right',
  '.float-subscribe',
  '#connections',
  'footer',
  '.weather.widget',
  '.widget.subscribe',
  '.widget.partners',
  '.widget.trending-news',
  '.widget.affix-ad',
  '.well.related-news',
  '.widget.latest-news',
  'ol.breadcrumb',
  '.social-share',
  '.social-apps',
  '.rate-bar',
  '.article-meta .pull-left',
  '.article-meta .pull-right',
  '.main > br',
  '.main > hr',
].forEach((selector) => {
  document.querySelectorAll(selector).forEach(hideElement);
});

const main = document.querySelector('.main');
const articleWrap = document.querySelector('.article-wrap');
if (main && articleWrap) {
  Array.from(main.children).forEach((child) => {
    if (child !== articleWrap) {
      hideElement(child);
    }
  });
  main.style.setProperty('padding-top', '12px', 'important');
  main.style.setProperty('width', '100%', 'important');
  main.style.setProperty('max-width', '100%', 'important');
}

if (articleWrap) {
  articleWrap.style.setProperty('width', '100%', 'important');
  articleWrap.style.setProperty('max-width', '100%', 'important');
  articleWrap.style.setProperty('margin', '0 auto', 'important');
}

const article = document.querySelector('article.article');
if (article) {
  article.style.setProperty('width', '100%', 'important');
  article.style.setProperty('max-width', '100%', 'important');
  article.style.setProperty('margin', '0', 'important');
}

const contentCol = document.querySelector('.col-md-8, .col-lg-8');
if (contentCol) {
  contentCol.style.setProperty('width', '100%', 'important');
  contentCol.style.setProperty('max-width', '100%', 'important');
  contentCol.style.setProperty('flex', '0 0 100%', 'important');
}
        """
        try:
            driver.execute_script(script)
        except BrowserError:
            pass

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        items = self._select_recent_items(soup)
        hits: list[SearchHit] = []

        for item in items:
            link = item.select_one("a[href]")
            if not link:
                continue

            href = link.get("href")
            if not href:
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            h3 = link.select_one("h3")
            title = h3.get_text(strip=True) if h3 else link.get_text(strip=True) or None

            published_at = self._extract_listing_date(item) or self._extract_date_from_image(link)
            snippet = self._extract_snippet(item)

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

    def _build_news_page_urls(self) -> list[str]:
        page_limit = max(self.config.max_pages, self.MAX_NEWS_PAGES)
        urls = [self.NEWS_URL]
        for page in range(2, page_limit + 1):
            urls.append(f"{self.NEWS_URL}/page/{page}")
        return urls

    def _select_recent_items(self, soup: BeautifulSoup) -> list:
        headline = next(
            (
                node
                for node in soup.select("h1.widget-title, h1")
                if "all headlines" in node.get_text(" ", strip=True).lower()
            ),
            None,
        )
        if headline:
            next_list = headline.find_next_sibling("ul", class_="grid")
            if next_list:
                items = next_list.select("li")
                if items:
                    return items
        return soup.select("ul.grid > li")

    def _extract_listing_date(self, item) -> Optional[datetime]:
        timestamp = item.select_one(".item-meta .timestamp, .timestamp")
        if not timestamp:
            return None
        raw_value = " ".join(timestamp.get_text(" ", strip=True).split())
        return parse_date(raw_value) if raw_value else None

    def _extract_snippet(self, item) -> Optional[str]:
        paragraph = item.select_one("p")
        if not paragraph:
            return None
        snippet = " ".join(paragraph.get_text(" ", strip=True).split())
        return snippet or None

    def _page_reached_cutoff(self, page_hits: list[SearchHit], cutoff_datetime: datetime) -> bool:
        dated_hits = [hit.published_at for hit in page_hits if hit.published_at is not None]
        if not dated_hits:
            return False
        oldest = min(
            (
                value if value.tzinfo is not None else value.replace(tzinfo=cutoff_datetime.tzinfo)
            )
            for value in dated_hits
        )
        return oldest.astimezone(cutoff_datetime.tzinfo) < cutoff_datetime

    def _extract_date_from_image(self, element) -> Optional[datetime]:
        img = element.select_one("img")
        if not img:
            return None

        # Check background-image style first, then src
        style = img.get("style", "")
        src = img.get("src", "")
        for source in (style, src):
            match = _IMG_DATE_RE.search(source)
            if match:
                try:
                    return datetime(
                        int(match.group(1)),
                        int(match.group(2)),
                        int(match.group(3)),
                        tzinfo=timezone.utc,
                    )
                except ValueError:
                    pass
        return None
