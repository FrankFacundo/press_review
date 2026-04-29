from __future__ import annotations

import logging
import random
import string
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from bs4 import BeautifulSoup
from luxnews.browser_types import BrowserTimeoutError, BrowserError

from luxnews.config import RunConfig
from luxnews.debug import DebugManager, DebugOptions
from luxnews.media.base import BaseMediaScraper
from luxnews.media.factory import build_media_scraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.models import ArticleRecord, MediaStatus, SearchHit
from luxnews.pdf_utils import build_run_summary_pdf, merge_pdfs, stamp_article_pdf_header
from luxnews.browser_utils import (
    highlight_keywords_on_page,
    create_driver,
    extract_title,
    extract_visible_text,
    extract_visible_text_from_selectors,
    login_contacto,
    login_lessentiel,
    login_luxtimes,
    login_wort,
    print_to_pdf,
    reserve_space_for_pdf_header,
    try_accept_cookies,
    wait_for_ready,
)
from luxnews.utils import (
    dump_json,
    ensure_dir,
    matches_keyword_with_exclusions,
    normalize_text,
    parse_date,
    safe_filename,
    unique_preserve_order,
)

LOGGER = logging.getLogger(__name__)

ARTICLE_KEYWORD_VALIDATED_MEDIA_IDS = {
    "rtl.lu",
    "today.rtl.lu",
    "infos.rtl.lu",
}

LUXTIMES_MEDIA_IDS = {
    "luxtimes.lu",
    "luxtimes.lu/en",
}


class LuxNewsRunner:
    def __init__(self, config: RunConfig, progress_callback: Optional[Callable[[dict], None]] = None):
        self.config = config
        self.progress_callback = progress_callback
        self._wort_login_attempted = False
        self._wort_login_success = False
        self._luxtimes_login_attempted = False
        self._luxtimes_login_success = False
        self._lessentiel_login_attempted = False
        self._lessentiel_login_success = False
        self._contacto_login_attempted = False
        self._contacto_login_success = False

    def run_job(self, job_name: Optional[str] = None) -> dict:
        run_id = self._generate_run_id(job_name)
        run_timestamp = datetime.now(timezone.utc).isoformat()
        search_cutoff = self.config.resolve_search_cutoff()

        output_root = ensure_dir(Path(self.config.output_dir))
        run_dir = ensure_dir(output_root / run_id)
        pdf_dir = ensure_dir(run_dir / "pdfs")

        debug_manager = DebugManager(
            DebugOptions(enabled=self.config.debug, output_dir=output_root, run_id=run_id)
        )

        driver = create_driver(
            self.config.driver,
            self.config.headless,
            self.config.open_devtools,
            enable_logging=self.config.debug,
            page_timeout=self.config.page_timeout,
        )

        records: list[ArticleRecord] = []
        media_statuses: list[MediaStatus] = []
        article_pdf_paths: list[Path] = []

        try:
            for index, media_id in enumerate(self.config.medias, start=1):
                status = MediaStatus(media=media_id, status="ok", errors=[])
                self._notify({"event": "media_start", "media": media_id, "index": index})
                try:
                    scraper = self._get_scraper(media_id)
                except KeyError as exc:
                    status.status = "failed"
                    status.errors.append(str(exc))
                    media_statuses.append(status)
                    self._notify({"event": "media_error", "media": media_id, "error": str(exc)})
                    continue

                if media_id == "wort.lu":
                    wort_login_ok = self._ensure_wort_login(driver)
                    if not wort_login_ok:
                        status.status = "failed"
                        status.errors.append(
                            "Wort login failed. Set WORT_USERNAME and WORT_PASSWORD in .env."
                        )
                        media_statuses.append(status)
                        self._notify(
                            {
                                "event": "media_error",
                                "media": media_id,
                                "error": "Wort login failed",
                            }
                        )
                        continue

                if media_id in LUXTIMES_MEDIA_IDS:
                    luxtimes_login_ok = self._ensure_luxtimes_login(driver)
                    if not luxtimes_login_ok:
                        status.status = "failed"
                        status.errors.append(
                            "LuxTimes login failed. Set WORT_USERNAME and WORT_PASSWORD in .env."
                        )
                        media_statuses.append(status)
                        self._notify(
                            {
                                "event": "media_error",
                                "media": media_id,
                                "error": "LuxTimes login failed",
                            }
                        )
                        continue

                if media_id in {"lessentiel.lu", "lessentiel.lu/fr"}:
                    lessentiel_login_ok = self._ensure_lessentiel_login(driver)
                    if not lessentiel_login_ok:
                        status.status = "partial"
                        status.errors.append(
                            "Lessentiel login could not be fully completed (credentials missing or email-code verification required). Continuing with available search results."
                        )
                        self._notify(
                            {
                                "event": "media_error",
                                "media": media_id,
                                "error": "Lessentiel login failed",
                            }
                        )

                if media_id == "contacto.lu":
                    contacto_login_ok = self._ensure_contacto_login(driver)
                    if not contacto_login_ok:
                        status.status = "failed"
                        status.errors.append(self._contacto_login_error_message())
                        media_statuses.append(status)
                        self._notify(
                            {
                                "event": "media_error",
                                "media": media_id,
                                "error": "Contacto login failed",
                            }
                        )
                        continue

                try:
                    results = self._collect_search_hits(
                        scraper,
                        driver,
                        debug_manager,
                        cutoff_datetime=search_cutoff,
                    )
                except Exception as exc:  # noqa: BLE001
                    status.status = "failed"
                    status.errors.append(f"Search failed for {media_id}: {exc}")
                    media_statuses.append(status)
                    self._notify({"event": "media_error", "media": media_id, "error": str(exc)})
                    continue

                for url, payload in results.items():
                    record = self._process_article(
                        driver=driver,
                        debug_manager=debug_manager,
                        scraper=scraper,
                        media_id=media_id,
                        url=url,
                        keywords=self.config.keywords,
                        snippets=payload.get("snippets", []),
                        search_title=payload.get("title"),
                        search_date=payload.get("published_at"),
                        pdf_dir=pdf_dir,
                        run_id=run_id,
                        run_timestamp=run_timestamp,
                    )
                    records.append(record)
                    if record.status == "ok" and record.per_article_pdf_path:
                        article_pdf_paths.append(Path(record.per_article_pdf_path))
                    if record.status == "failed":
                        status.status = "partial"
                        status.errors.extend(record.errors)
                    time.sleep(self.config.rate_limit_seconds)

                media_statuses.append(status)
                self._notify(
                    {
                        "event": "media_done",
                        "media": media_id,
                        "status": status.status,
                        "errors": status.errors,
                    }
                )
        finally:
            driver.quit()

        summary_pdf = run_dir / "summary.pdf"
        merged_pdf = run_dir / "merged.pdf"
        matches_json = run_dir / "matches.json"

        article_rows = []
        for record in records:
            if record.status != "ok":
                continue
            article_rows.append(
                [
                    record.media,
                    record.published_at or "",
                    record.title or "",
                    record.url,
                    ", ".join(record.matched_keywords),
                ]
            )

        build_run_summary_pdf(
            summary_pdf,
            run_id=run_id,
            run_timestamp=run_timestamp,
            search_cutoff=search_cutoff,
            business_days_before=self.config.business_days_before,
            cutoff_hour=self.config.cutoff_hour,
            medias=self.config.medias,
            keywords=self.config.keywords,
            media_statuses=[asdict(status) for status in media_statuses],
            article_rows=article_rows,
        )

        merge_pdfs([summary_pdf] + article_pdf_paths, merged_pdf)
        dump_json(matches_json, [asdict(record) for record in records])

        return {
            "run_id": run_id,
            "run_timestamp": run_timestamp,
            "run_dir": str(run_dir),
            "summary_pdf": str(summary_pdf),
            "merged_pdf": str(merged_pdf),
            "matches_json": str(matches_json),
            "records": records,
            "media_statuses": media_statuses,
        }

    def _collect_search_hits(
        self,
        scraper: BaseMediaScraper,
        driver,
        debug_manager: DebugManager,
        cutoff_datetime: datetime,
    ) -> dict[str, dict]:
        if (
            scraper.definition.media_id == "paperjam.lu"
            and isinstance(scraper, PaperjamMediaScraper)
        ):
            return self._collect_paperjam_hits(scraper, driver, debug_manager, cutoff_datetime)

        hits_by_url: dict[str, dict] = {}
        use_browser = scraper.requires_browser_search() or (
            (self.config.search_use_browser or self.config.debug)
            and not scraper.prefers_plain_search()
        )

        for keyword in self.config.keywords:
            if use_browser:
                keyword_hits = self._search_with_browser(
                    scraper, driver, debug_manager, keyword, cutoff_datetime
                )
            else:
                keyword_hits = scraper.search(keyword, cutoff_datetime)
            for hit in keyword_hits:
                if self._requires_article_keyword_validation(scraper) and not (
                    self._search_hit_matches_keyword(
                        scraper=scraper,
                        driver=driver,
                        debug_manager=debug_manager,
                        hit=hit,
                        keyword=keyword,
                    )
                ):
                    continue
                payload = hits_by_url.setdefault(
                    hit.url,
                    {
                        "keywords": set(),
                        "snippets": [],
                        "title": hit.title,
                        "published_at": hit.published_at,
                    },
                )
                payload["keywords"].add(keyword)
                if hit.snippet:
                    payload["snippets"].append(hit.snippet)
                if hit.title and not payload.get("title"):
                    payload["title"] = hit.title
                if hit.published_at and not payload.get("published_at"):
                    payload["published_at"] = hit.published_at

        for payload in hits_by_url.values():
            payload["snippets"] = unique_preserve_order(payload["snippets"])
        return hits_by_url

    def _requires_article_keyword_validation(self, scraper: BaseMediaScraper) -> bool:
        return scraper.definition.media_id in ARTICLE_KEYWORD_VALIDATED_MEDIA_IDS

    def _search_hit_matches_keyword(
        self,
        scraper: BaseMediaScraper,
        driver,
        debug_manager: DebugManager,
        hit: SearchHit,
        keyword: str,
    ) -> bool:
        try:
            self._open_page_best_effort(driver, hit.url)
            try_accept_cookies(driver)

            article_page_urls = unique_preserve_order(
                scraper.collect_article_page_urls(driver, hit.url)
            )
            if not article_page_urls:
                article_page_urls = [hit.url]

            debug_manager.dump_page(
                driver,
                media=scraper.definition.media_id,
                kind="search-hit-article-check",
                url=hit.url,
                selectors=MEDIA_REGISTRY[scraper.definition.media_id].debug_selectors.get(
                    "article", []
                ),
            )

            visible_text = self._collect_article_visible_texts(
                driver=driver,
                media_id=scraper.definition.media_id,
                page_urls=article_page_urls,
            )
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning(
                "Search hit article keyword validation failed for %s (%s): %s",
                hit.url,
                keyword,
                exc,
            )
            return False

        return matches_keyword_with_exclusions(normalize_text(visible_text), keyword)

    def _collect_paperjam_hits(
        self,
        scraper: PaperjamMediaScraper,
        driver,
        debug_manager: DebugManager,
        cutoff_datetime: datetime,
    ) -> dict[str, dict]:
        hits_by_url: dict[str, dict] = {}
        for keyword in self.config.keywords:
            urls = scraper.build_search_urls(keyword, search_cutoff=cutoff_datetime)

            for url in urls:
                driver.get(url)
                wait_for_ready(driver, self.config.wait_timeout)
                try_accept_cookies(driver)

                debug_manager.dump_page(
                    driver,
                    media=scraper.definition.media_id,
                    kind="search",
                    url=url,
                    selectors=scraper.definition.debug_selectors.get("search", []),
                )

                html = driver.page_source
                page_hits = scraper.parse_search_results(html, url)
                page_hits = scraper.filter_hits_by_date(page_hits, cutoff_datetime=cutoff_datetime)

                # End when pagination reaches a page without article cards.
                if not page_hits:
                    break

                for hit in page_hits:
                    payload = hits_by_url.setdefault(
                        hit.url,
                        {
                            "keywords": set(),
                            "snippets": [],
                            "title": hit.title,
                            "published_at": hit.published_at,
                        },
                    )
                    payload["keywords"].add(keyword)
                    if hit.snippet:
                        payload["snippets"].append(hit.snippet)
                    if hit.title and not payload.get("title"):
                        payload["title"] = hit.title
                    if hit.published_at and not payload.get("published_at"):
                        payload["published_at"] = hit.published_at

                if self.config.pause:
                    self._pause("Search page loaded. Press Enter to continue...")
                if len(hits_by_url) >= self.config.max_results:
                    break
                time.sleep(self.config.rate_limit_seconds)

            if len(hits_by_url) >= self.config.max_results:
                break

        for payload in hits_by_url.values():
            payload["snippets"] = unique_preserve_order(payload["snippets"])
        return hits_by_url

    def _search_with_browser(
        self,
        scraper: BaseMediaScraper,
        driver,
        debug_manager: DebugManager,
        keyword: str,
        cutoff_datetime: datetime,
    ):
        hits = []
        seen_urls: set[str] = set()
        urls = scraper.build_search_urls(keyword)
        pages_seen: set[str] = set()

        for url in urls:
            if url in pages_seen:
                continue
            pages_seen.add(url)
            driver.get(url)
            wait_for_ready(driver, self.config.wait_timeout)
            try_accept_cookies(driver)
            scraper.prepare_browser_search_page(driver, keyword, self.config.wait_timeout)
            try_accept_cookies(driver)

            debug_manager.dump_page(
                driver,
                media=scraper.definition.media_id,
                kind="search",
                url=url,
                selectors=scraper.definition.debug_selectors.get("search", []),
            )

            html = driver.page_source
            page_hits = scraper.parse_search_results(html, url)
            page_hits = scraper.filter_hits_by_date(page_hits, cutoff_datetime=cutoff_datetime)
            new_hits = [hit for hit in page_hits if hit.url not in seen_urls]
            for hit in new_hits:
                seen_urls.add(hit.url)
            hits.extend(new_hits)

            if not new_hits:
                break
            if self.config.pause:
                self._pause("Search page loaded. Press Enter to continue...")

            if len(hits) >= self.config.max_results:
                break
            if "{page}" not in scraper.definition.search_url:
                if len(pages_seen) >= self.config.max_pages:
                    break
                next_url = scraper.detect_next_page(html, url)
                if not next_url or next_url in pages_seen:
                    break
                urls.append(next_url)
            time.sleep(self.config.rate_limit_seconds)
        return hits

    def _ensure_wort_login(self, driver) -> bool:
        if self._wort_login_attempted:
            return self._wort_login_success

        self._wort_login_attempted = True
        username = (self.config.wort_username or "").strip()
        password = self.config.wort_password or ""
        if not username or not password:
            self._wort_login_success = False
            return False

        self._wort_login_success = login_wort(
            driver=driver,
            username=username,
            password=password,
            wait_timeout=self.config.wait_timeout,
        )
        return self._wort_login_success

    def _ensure_luxtimes_login(self, driver) -> bool:
        if self._luxtimes_login_attempted:
            return self._luxtimes_login_success

        self._luxtimes_login_attempted = True
        username = (self.config.wort_username or "").strip()
        password = self.config.wort_password or ""
        if not username or not password:
            self._luxtimes_login_success = False
            return False

        self._luxtimes_login_success = login_luxtimes(
            driver=driver,
            username=username,
            password=password,
            wait_timeout=self.config.wait_timeout,
        )
        return self._luxtimes_login_success

    def _ensure_lessentiel_login(self, driver) -> bool:
        if self._lessentiel_login_attempted:
            return self._lessentiel_login_success

        self._lessentiel_login_attempted = True
        email = (self.config.lessentiel_email or "").strip()
        password = self.config.lessentiel_password or ""
        if not email or not password:
            self._lessentiel_login_success = False
            return False

        self._lessentiel_login_success = login_lessentiel(
            driver=driver,
            email=email,
            password=password,
            wait_timeout=self.config.wait_timeout,
        )
        return self._lessentiel_login_success

    def _ensure_contacto_login(self, driver) -> bool:
        if self._contacto_login_attempted:
            return self._contacto_login_success

        self._contacto_login_attempted = True
        email = (self.config.contacto_email or "").strip()
        password = self.config.contacto_password or ""
        if not email or not password:
            self._contacto_login_success = False
            return False

        self._contacto_login_success = login_contacto(
            driver=driver,
            email=email,
            password=password,
            wait_timeout=self.config.wait_timeout,
        )
        return self._contacto_login_success

    def _contacto_login_error_message(self) -> str:
        email = (self.config.contacto_email or "").strip()
        password = self.config.contacto_password or ""
        if not email or not password:
            return (
                "Contacto login failed. Set CONTACTO_EMAIL and CONTACTO_PASSWORD "
                "or WORT_USERNAME and WORT_PASSWORD in .env."
            )
        return (
            "Contacto login failed with configured credentials. Check account access, "
            "password validity, or whether the login flow now requires verification."
        )

    def _process_article(
        self,
        driver,
        debug_manager: DebugManager,
        scraper: "BaseMediaScraper",
        media_id: str,
        url: str,
        keywords: list[str],
        snippets: list[str],
        search_title: Optional[str],
        search_date: Optional[datetime],
        pdf_dir: Path,
        run_id: str,
        run_timestamp: str,
    ) -> ArticleRecord:
        errors: list[str] = []
        per_article_pdf_path: Optional[str] = None
        title: Optional[str] = search_title
        published_at: Optional[str] = None
        date_unknown = True
        article_page_urls = [url]

        try:
            self._open_page_best_effort(driver, url)
            try_accept_cookies(driver)

            detected_title = extract_title(driver)
            if detected_title:
                title = detected_title

            detected_date = self._extract_date(driver.page_source)
            if detected_date:
                published_at = detected_date
                date_unknown = False
            elif search_date:
                published_at = search_date.astimezone(timezone.utc).isoformat()
                date_unknown = False

            article_page_urls = unique_preserve_order(scraper.collect_article_page_urls(driver, url))
            if not article_page_urls:
                article_page_urls = [url]

            debug_manager.dump_page(
                driver,
                media=media_id,
                kind="article",
                url=url,
                selectors=MEDIA_REGISTRY[media_id].debug_selectors.get("article", []),
                detected_date=published_at,
            )

            if self.config.pause:
                self._pause("Article page loaded. Press Enter to continue...")

            combined_visible_text = self._collect_article_visible_texts(
                driver=driver,
                media_id=media_id,
                page_urls=article_page_urls,
            )
            normalized_text = normalize_text(combined_visible_text)
            matched_keywords = [
                kw for kw in keywords if matches_keyword_with_exclusions(normalized_text, kw)
            ]

            if not snippets and combined_visible_text:
                snippet_text = " ".join(combined_visible_text.split())[:200]
                if snippet_text:
                    snippets = [snippet_text]

            if not matched_keywords:
                return ArticleRecord(
                    run_id=run_id,
                    run_timestamp=run_timestamp,
                    media=media_id,
                    url=url,
                    title=title,
                    published_at=published_at,
                    date_unknown=date_unknown,
                    matched_keywords=[],
                    snippets=snippets,
                    per_article_pdf_path=None,
                    status="skipped",
                    errors=["No keyword match found in visible text."],
                )

            safe_media_id = safe_filename(media_id)
            safe_title = safe_filename(title or url)
            pdf_path = pdf_dir / f"{safe_media_id}_{safe_title}.pdf"
            per_article_pdf_path = self._render_article_pdf(
                driver=driver,
                scraper=scraper,
                media_id=media_id,
                page_urls=article_page_urls,
                matched_keywords=matched_keywords,
                output_path=pdf_path,
                published_at=published_at,
            )

            return ArticleRecord(
                run_id=run_id,
                run_timestamp=run_timestamp,
                media=media_id,
                url=url,
                title=title,
                published_at=published_at,
                date_unknown=date_unknown,
                matched_keywords=matched_keywords,
                snippets=snippets,
                per_article_pdf_path=per_article_pdf_path,
                status="ok",
                errors=[],
            )
        except Exception as exc:  # noqa: BLE001
            if self.config.pause_on_error:
                self._pause("Error encountered. Press Enter to continue...")
            errors.append(f"{exc}")
            errors.extend(self._format_error_artifacts(driver, media_id, url, run_id))
            return ArticleRecord(
                run_id=run_id,
                run_timestamp=run_timestamp,
                media=media_id,
                url=url,
                title=title,
                published_at=published_at,
                date_unknown=date_unknown,
                matched_keywords=[],
                snippets=snippets,
                per_article_pdf_path=per_article_pdf_path,
                status="failed",
                errors=errors,
            )

    def _collect_article_visible_texts(
        self,
        driver,
        media_id: str,
        page_urls: list[str],
    ) -> str:
        texts: list[str] = []

        for index, page_url in enumerate(page_urls):
            if index > 0:
                self._open_page_best_effort(driver, page_url)
                try_accept_cookies(driver)
            visible_text = self._extract_visible_text_for_media(driver, media_id)
            if visible_text:
                texts.append(visible_text)

        return "\n\n".join(texts)

    def _render_article_pdf(
        self,
        driver,
        scraper: "BaseMediaScraper",
        media_id: str,
        page_urls: list[str],
        matched_keywords: list[str],
        output_path: Path,
        published_at: Optional[str],
    ) -> str:
        temp_paths: list[Path] = []

        try:
            for index, page_url in enumerate(page_urls, start=1):
                self._open_page_best_effort(driver, page_url)
                try_accept_cookies(driver)
                scraper.prepare_article_for_pdf(driver)
                reserve_space_for_pdf_header(driver)
                highlight_keywords_on_page(driver, matched_keywords)

                if len(page_urls) == 1:
                    page_output_path = output_path
                else:
                    page_output_path = output_path.with_name(
                        f"{output_path.stem}__page{index}{output_path.suffix}"
                    )
                    temp_paths.append(page_output_path)

                print_to_pdf(driver, page_output_path)

            if temp_paths:
                merge_pdfs(temp_paths, output_path)

            stamp_article_pdf_header(output_path, media_id, published_at)
            return str(output_path)
        finally:
            for temp_path in temp_paths:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    continue

    def _open_page_best_effort(self, driver, url: str) -> None:
        try:
            driver.get(url)
            wait_for_ready(driver, self.config.wait_timeout)
            return
        except BrowserTimeoutError as exc:
            LOGGER.warning("Page load timeout for %s: %s", url, exc)
            self._stop_page_load(driver)
            return
        except BrowserError as exc:
            if self._is_renderer_timeout_error(exc):
                LOGGER.warning("Renderer timeout for %s: %s", url, exc)
                self._stop_page_load(driver)
                return
            raise

    def _stop_page_load(self, driver) -> None:
        try:
            driver.execute_script("window.stop();")
        except BrowserError:
            return

    def _is_renderer_timeout_error(self, exc: Exception) -> bool:
        message = str(exc).casefold()
        return "timed out receiving message from renderer" in message

    def _extract_visible_text_for_media(self, driver, media_id: str) -> str:
        if media_id == "paperjam.lu":
            return extract_visible_text_from_selectors(
                driver,
                selectors=[
                    "main article .article-content",
                    "article .article-content",
                    ".article-content",
                    "main article",
                    "article",
                ],
                fallback_to_body=False,
            )
        if media_id == "lequotidien.lu":
            return extract_visible_text_from_selectors(
                driver,
                selectors=[
                    "#main-content .content article.post-listing .entry",
                    "article.post-listing .entry",
                    ".post-listing .entry",
                ],
                fallback_to_body=False,
            )
        if media_id == "contacto.lu":
            return extract_visible_text_from_selectors(
                driver,
                selectors=[
                    "article section[data-testid='article-body']",
                    "section[data-testid='article-body']",
                ],
                fallback_to_body=False,
            )
        if media_id == "chronicle.lu":
            return extract_visible_text_from_selectors(
                driver,
                selectors=[
                    ".article-wrap article.article",
                    "article.article",
                    ".article-wrap",
                ],
                fallback_to_body=False,
            )
        if media_id in {"rtl.lu", "today.rtl.lu", "infos.rtl.lu"}:
            return self._extract_rtl_article_visible_text(driver)
        return extract_visible_text(driver)

    def _extract_rtl_article_visible_text(self, driver) -> str:
        script = r"""
const root = document.querySelector("[class*='ArticleDefault_article__']");
if (!root) return '';
const stopPatterns = [
  'also today',
  "plus d'actus",
  "plus d'actualit",
  'méi noriichten',
  'mehr nachrichten',
];
const headings = root.querySelectorAll('h1, h2, h3, h4');
for (const h of headings) {
  const txt = (h.textContent || '').trim().toLowerCase();
  if (stopPatterns.some((p) => txt === p || txt.startsWith(p))) {
    let node = h;
    while (node) {
      const next = node.nextElementSibling;
      node.style.setProperty('display', 'none', 'important');
      node = next;
    }
    break;
  }
}
return (root.innerText || '').trim();
"""
        try:
            result = driver.execute_script(script)
        except BrowserError:
            return ""
        return result if isinstance(result, str) else ""

    def _extract_date(self, html: str) -> Optional[str]:
        # Best-effort parsing from common meta tags or time elements.
        soup = BeautifulSoup(html, "lxml")
        meta_keys = [
            "article:published_time",
            "og:pubdate",
            "pubdate",
            "date",
            "publish_date",
            "dc.date",
        ]
        for key in meta_keys:
            tag = soup.find("meta", attrs={"property": key}) or soup.find(
                "meta", attrs={"name": key}
            )
            if tag and tag.get("content"):
                parsed = parse_date(tag["content"])
                if parsed:
                    return parsed.astimezone(timezone.utc).isoformat()

        time_tag = soup.find("time")
        if time_tag:
            date_text = time_tag.get("datetime") or time_tag.get_text(strip=True)
            parsed = parse_date(date_text)
            if parsed:
                return parsed.astimezone(timezone.utc).isoformat()
        return None

    def _format_error_artifacts(self, driver, media_id: str, url: str, run_id: str) -> list[str]:
        errors: list[str] = []
        try:
            output_root = ensure_dir(Path(self.config.output_dir))
            safe_media_id = safe_filename(media_id)
            error_dir = ensure_dir(output_root / "errors" / run_id / safe_media_id)
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            html_path = error_dir / f"{timestamp}_page.html"
            html_path.write_text(driver.page_source or "", encoding="utf-8")
            screenshot_path = error_dir / f"{timestamp}_page.png"
            try:
                driver.save_screenshot(str(screenshot_path))
            except BrowserError:
                screenshot_path = None
            errors.append(f"URL: {url}")
            if screenshot_path:
                errors.append(f"Screenshot: {screenshot_path}")
            errors.append(f"HTML: {html_path}")
        except Exception as exc:  # noqa: BLE001
            errors.append(f"Artifact capture failed: {exc}")
        return errors

    def _get_scraper(self, media_id: str) -> BaseMediaScraper:
        definition = MEDIA_REGISTRY.get(media_id)
        if not definition:
            raise KeyError(f"Unknown media: {media_id}")
        return build_media_scraper(definition, self.config)

    def _generate_run_id(self, job_name: Optional[str]) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
        if job_name:
            return f"{job_name}_{timestamp}_{suffix}"
        return f"run_{timestamp}_{suffix}"

    def _pause(self, message: str) -> None:
        try:
            input(message)
        except EOFError:
            return

    def _notify(self, payload: dict) -> None:
        if not self.progress_callback:
            return
        try:
            self.progress_callback(payload)
        except Exception:  # noqa: BLE001
            return
