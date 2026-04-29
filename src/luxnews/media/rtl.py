from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
from urllib.parse import quote_plus

from bs4 import BeautifulSoup
from luxnews.browser_types import BrowserError

from luxnews.media.base import BaseMediaScraper
from luxnews.models import SearchHit
from luxnews.utils import parse_date, to_absolute_url


class RTLMediaScraper(BaseMediaScraper):
    DATE_FMT_SEARCH = "%d.%m.%Y"
    API_TEMPLATE = "https://www-api.rtl.lu/search?q={query}&p={page}"

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
  el.style.setProperty("min-height", "0", "important");
  el.style.setProperty("margin", "0", "important");
  el.style.setProperty("padding", "0", "important");
  el.setAttribute("aria-hidden", "true");
};

const hideSelectors = [
  // Right-hand "Am meeschte gelies" sidebar and its sticky wrapper.
  "#aside",
  "[class*='TwoColumnContainer_aside__']",
  "[class*='StickyAsideElementWrapper_']",
  // Ad banners (Adnuntius) — leaderboard, halfpage, inpage, native, etc.
  "[class*='AdnuntiusAd_']",
  "[class*='FallbackAdnuntiusAd_']",
  ".adnuntius-ad",
  "[class*='ad-slot--']",
  "[class*='ad-slot__']",
  "[id^='ldb-']",
  "[id^='halfpage-']",
  // OneSignal push/topic subscription prompts.
  "#onesignal-slidedown-container",
  ".onesignal-slidedown-container",
  ".onesignal-slidedown-dialog",
  ".onesignal-customlink-container",
  ".onesignal-bell-container",
  ".onesignal-reset-container",
  "[id*='notification-modal']",
  "[id*='notifications-modal']",
  "[id*='notification-overlay']",
  "[id*='notifications-overlay']",
  "[class*='notification'][class*='modal']",
  "[class*='notifications'][class*='modal']",
  "[class*='notification'][class*='overlay']",
  "[class*='notifications'][class*='overlay']",
  ".modal-backdrop",
  ".backdrop",
  "[class*='modal-backdrop']",
  // Related / more-news blocks and global footer widgets.
  "[class*='ContentList_PageListArticleMoreSplitTop__']",
  "[class*='ContentList_PageListArticleMoreSplitBottom__']",
  "[class*='BaseFooter_container__']",
  "[class*='BackToTop_backToTop__']",
  // Reader comments block ("Commentairen").
  "[class*='Comments_container__']",
];
hideSelectors.forEach((selector) => {
  document.querySelectorAll(selector).forEach(hideElement);
});

// Hide any DOM nodes that sit between <body> and <header> — the hoverboard
// ad container lives there and keeps reserving space even after its inner
// div is hidden.
const headerEl = document.querySelector("header");
if (headerEl && document.body) {
  let node = document.body.firstElementChild;
  while (node && node !== headerEl && !node.contains(headerEl)) {
    hideElement(node);
    node = node.nextElementSibling;
  }
}

// Adnuntius occasionally renders into top-level iframes — drop them too.
document.querySelectorAll("iframe").forEach((frame) => {
  const src = (frame.getAttribute("src") || "").toLowerCase();
  const id = (frame.getAttribute("id") || "").toLowerCase();
  const name = (frame.getAttribute("name") || "").toLowerCase();
  if (
    src.includes("adnuntius") ||
    src.includes("/ad/") ||
    id.includes("ad") ||
    name.includes("ad")
  ) {
    hideElement(frame);
  }
});

// Dismiss any remaining modal / topic-subscription popups whose label
// mentions notifications or the localized Akzeptéieren / Ofbriechen buttons.
const modalCandidates = document.querySelectorAll(
  "[role='dialog'], [aria-modal='true'], dialog"
);
modalCandidates.forEach((el) => {
  const style = window.getComputedStyle(el);
  const isOverlayLike =
    style.position === "fixed" ||
    style.position === "sticky" ||
    el.getAttribute("role") === "dialog" ||
    el.hasAttribute("aria-modal");
  if (!isOverlayLike) return;
  const text = (el.innerText || "").toLowerCase();
  if (
    text.includes("akzeptéieren") ||
    text.includes("ofbriechen") ||
    text.includes("notifications") ||
    text.includes("allow") ||
    text.includes("not now")
  ) {
    hideElement(el);
  }
});

// Hide any fixed-position leftover panel that overlaps the article
// (covers the topic-subscription popup on rtl.lu article pages).
document.querySelectorAll("body *").forEach((el) => {
  const style = window.getComputedStyle(el);
  if (style.position !== "fixed") return;
  const rect = el.getBoundingClientRect();
  if (rect.width < 200 || rect.height < 120) return;
  const text = (el.innerText || "").toLowerCase();
  if (
    text.includes("akzeptéieren") ||
    text.includes("ofbriechen") ||
    text.includes("fotosgalerien")
  ) {
    hideElement(el);
  }
});

// Hide "Also today" subsection embedded inside daily-digest articles
// (today.rtl.lu / rtl.lu daily roundups wrap a list of unrelated stories
// under an h2 — drop that h2 and every following sibling).
const alsoTodayPatterns = [
  "also today",
  "plus d'actus",
  "plus d'actualit",
  "méi noriichten",
  "mehr nachrichten",
];
document
  .querySelectorAll(
    "[class*='ArticleDefault_article__'] h1, " +
    "[class*='ArticleDefault_article__'] h2, " +
    "[class*='ArticleDefault_article__'] h3, " +
    "[class*='ArticleDefault_article__'] h4"
  )
  .forEach((heading) => {
    const txt = (heading.textContent || "").trim().toLowerCase();
    if (!alsoTodayPatterns.some((p) => txt === p || txt.startsWith(p))) return;
    let node = heading;
    while (node) {
      const next = node.nextElementSibling;
      hideElement(node);
      node = next;
    }
  });

const relatedBlocks = document.querySelectorAll("[class*='ContentList_contentList__']");
relatedBlocks.forEach((el) => {
  const text = (el.innerText || "").toLowerCase();
  if (
    text.includes("am meeschte gelies") ||
    text.includes("more news") ||
    text.includes("méi noriichten")
  ) {
    hideElement(el);
  }
});

if (document.body) {
  document.body.style.setProperty("overflow", "visible", "important");
  document.body.style.setProperty("position", "static", "important");
}
if (document.documentElement) {
  document.documentElement.style.setProperty("overflow", "visible", "important");
}
"""
        try:
            driver.execute_script(script)
        except BrowserError:
            return

    def build_search_urls(self, keyword: str) -> list[str]:
        query = quote_plus(keyword)
        return [
            self.API_TEMPLATE.format(query=query, page=page)
            for page in range(1, self.config.max_pages + 1)
        ]

    def parse_search_results(self, html: str, base_url: str) -> list[SearchHit]:
        payload = self._extract_json_payload(html)
        results = payload.get("content", {}).get("results", [])
        if isinstance(results, list):
            hits = self._build_hits_from_results(results, base_url)
            if hits:
                return hits
        return super().parse_search_results(html, base_url)

    def extract_date(self, html: str) -> datetime | None:  # noqa: D401
        soup = BeautifulSoup(html, "lxml")
        time_tag = soup.find("time")
        if time_tag and time_tag.has_attr("datetime"):
            try:
                value = time_tag["datetime"].replace("Z", "+00:00")
                return datetime.fromisoformat(value)
            except ValueError:  # malformed datetime
                pass

        date_tag = soup.select_one("a.rtl-search-res_date")
        if date_tag:
            try:
                return datetime.strptime(date_tag.get_text(strip=True), self.DATE_FMT_SEARCH)
            except ValueError:
                pass
        return None

    def _extract_date_text(self, element) -> Optional[str]:
        extracted = self.extract_date(str(element))
        if extracted:
            return extracted.isoformat()

        if hasattr(element, "parents"):
            for parent in element.parents:
                extracted = self.extract_date(str(parent))
                if extracted:
                    return extracted.isoformat()

        return super()._extract_date_text(element)

    def _extract_json_payload(self, html: str) -> dict:
        try:
            payload = json.loads(html)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _build_hits_from_results(self, results: list[dict], base_url: str) -> list[SearchHit]:
        hits: list[SearchHit] = []
        for item in results:
            if not isinstance(item, dict):
                continue

            href = item.get("url")
            if not isinstance(href, str) or not href.strip():
                continue

            url = to_absolute_url(base_url, href)
            if not self._is_allowed_url(url):
                continue

            published_at = None
            raw_date = item.get("publishDate")
            if isinstance(raw_date, str) and raw_date.strip():
                published_at = parse_date(raw_date)
            if published_at is None:
                continue

            raw_title = item.get("title")
            title = None
            if isinstance(raw_title, str):
                title = " ".join(raw_title.split()) or None

            snippet = None
            for key in ("header", "kicker"):
                raw_snippet = item.get(key)
                if not isinstance(raw_snippet, str):
                    continue
                cleaned = " ".join(raw_snippet.split())
                if cleaned:
                    snippet = cleaned
                    break

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
