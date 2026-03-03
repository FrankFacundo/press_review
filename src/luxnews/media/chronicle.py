from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup

from selenium.common.exceptions import WebDriverException

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import to_absolute_url

# Image URLs contain dates in two formats:
#   New: /images/2026/Mar/20260302_...
#   Old: /images/KA//20160129_...
_IMG_DATE_RE = re.compile(r"/images/.*?(\d{4})(\d{2})(\d{2})[_-]")


class ChronicleMediaScraper(BaseMediaScraper):
    def prefers_plain_search(self) -> bool:
        return True

    def prepare_article_for_pdf(self, driver) -> None:
        script = """
        var selectors = [
            'header#header',
            'nav.navbar',
            '.main-nav-wrap',
            '.social-share',
            '.social-apps',
            '.sidebar.right',
            '.float-subscribe',
            '#connections',
            '.rate-bar',
            'footer',
            '.weather.widget',
            '.widget.subscribe',
            '.widget.partners',
            '.widget.trending-news',
            '.widget.latest-news',
            '.widget.affix-ad'
        ];
        selectors.forEach(function(sel) {
            document.querySelectorAll(sel).forEach(function(el) {
                el.style.display = 'none';
            });
        });
        // Expand article content to full width
        var article = document.querySelector('article.article');
        if (article) {
            article.style.width = '100%';
            article.style.maxWidth = '100%';
        }
        var contentCol = document.querySelector('.col-md-8, .col-lg-8');
        if (contentCol) {
            contentCol.style.width = '100%';
            contentCol.style.maxWidth = '100%';
        }
        """
        try:
            driver.execute_script(script)
        except WebDriverException:
            pass

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        items = soup.select("ul.grid > li")
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

            published_at = self._extract_date_from_image(link)
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
