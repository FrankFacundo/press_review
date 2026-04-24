from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Optional

from bs4 import BeautifulSoup
from selenium.common.exceptions import WebDriverException

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class LeQuotidienMediaScraper(BaseMediaScraper):
    SEARCH_CARD_SELECTORS = [
        "article.item-list",
        ".post-listing article",
    ]
    DATE_PATTERN = re.compile(r"\b(\d{1,2}/\d{1,2}/\d{4})\b")

    def prepare_article_for_pdf(self, driver) -> None:
        script = """
        var hideSelectors = [
            '.top-nav',
            'header#theme-header',
            '#main-nav',
            '#leaderboard',
            '.ads-top',
            '.sidebar-narrow',
            '#sidebar',
            '#footer-widget-area',
            '#footer',
            'footer',
            '#mc_embed_shell',
            '#crumbs',
            '.heateor_sss_sharing_container',
            '.share-post',
            '[id^="div-gpt-ad-"]',
            '.imu'
        ];
        hideSelectors.forEach(function(sel) {
            document.querySelectorAll(sel).forEach(function(el) {
                el.style.display = 'none';
            });
        });

        var article =
            document.querySelector('#main-content .content article.post-listing') ||
            document.querySelector('article.post-listing.post') ||
            document.querySelector('article.post-listing');
        if (!article) {
            return;
        }

        article.querySelectorAll(
            '.heateor_sss_sharing_container, .share-post, [id^="div-gpt-ad-"], .imu, iframe'
        ).forEach(function(el) {
            el.style.display = 'none';
        });

        var contentCol = article.closest('.content') || document.querySelector('#main-content .content');
        if (contentCol) {
            Array.from(contentCol.children).forEach(function(child) {
                if (child !== article) {
                    child.style.display = 'none';
                }
            });
            contentCol.style.width = '100%';
            contentCol.style.maxWidth = '100%';
            contentCol.style.float = 'none';
            contentCol.style.margin = '0 auto';
        }

        var contentWrap = document.querySelector('#main-content .content-wrap');
        if (contentWrap) {
            contentWrap.style.width = '100%';
            contentWrap.style.maxWidth = '100%';
            contentWrap.style.display = 'block';
        }

        var mainContent = document.querySelector('#main-content');
        if (mainContent) {
            mainContent.style.width = '100%';
            mainContent.style.maxWidth = '100%';
            mainContent.style.margin = '0 auto';
        }

        article.style.width = '100%';
        article.style.maxWidth = '100%';
        article.style.margin = '0 auto';

        // Reserve space at the top so the PDF header stamp (text at ~14pt,
        // line at ~22pt from the page top) does not overlap article content.
        if (document.body) {
            document.body.style.setProperty('padding-top', '40px', 'important');
        }
        """
        try:
            driver.execute_script(script)
        except WebDriverException:
            pass

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        soup = BeautifulSoup(html, "lxml")
        cards = self._select_search_cards(soup)

        hits: list[SearchHit] = []
        for card in cards:
            link = card.select_one("h2.post-title a[href]") or card.select_one("a[href]")
            if not link:
                continue

            href = (link.get("href") or "").strip()
            if not href:
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            title = " ".join(link.get_text(" ", strip=True).split()) or None
            snippet = self._extract_card_snippet(card)
            date_text = self._extract_date_text(card)

            hits.append(
                SearchHit(
                    url=url,
                    title=title,
                    published_at=self._parse_search_date(date_text),
                    snippet=snippet,
                    media_id=self.definition.media_id,
                )
            )

        return hits

    def _select_search_cards(self, soup: BeautifulSoup) -> list:
        for selector in self.SEARCH_CARD_SELECTORS:
            cards = soup.select(selector)
            if cards:
                return cards
        return []

    def _extract_date_text(self, element) -> Optional[str]:
        if hasattr(element, "select_one"):
            date_node = element.select_one("span.tie-date")
            if date_node:
                value = date_node.get_text(" ", strip=True)
                if value:
                    return value
        return super()._extract_date_text(element)

    def _extract_card_snippet(self, card) -> Optional[str]:
        snippet_node = card.select_one(".entry p, .entry")
        if not snippet_node:
            return None
        snippet = " ".join(snippet_node.get_text(" ", strip=True).split())
        return snippet or None

    def _parse_search_date(self, raw: Optional[str]) -> Optional[datetime]:
        if not raw:
            return None

        normalized = " ".join(raw.split())
        match = self.DATE_PATTERN.search(normalized)
        if match:
            try:
                parsed = datetime.strptime(match.group(1), "%d/%m/%Y")
            except ValueError:
                parsed = None
            if parsed:
                return parsed.replace(tzinfo=timezone.utc)

        return parse_date(normalized)
