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
from selenium.common.exceptions import WebDriverException

from luxnews.config import RunConfig
from luxnews.debug import DebugManager, DebugOptions
from luxnews.media.base import BaseMediaScraper
from luxnews.media.factory import build_media_scraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.models import ArticleRecord, MediaStatus
from luxnews.pdf_utils import build_run_summary_pdf, merge_pdfs, stamp_article_pdf_header
from luxnews.selenium_utils import (
    highlight_keywords_on_page,
    create_driver,
    extract_title,
    extract_visible_text,
    extract_visible_text_from_selectors,
    login_contacto,
    login_lessentiel,
    login_wort,
    print_to_pdf,
    try_accept_cookies,
    wait_for_ready,
)
from luxnews.utils import (
    contains_whole_keyword,
    dump_json,
    ensure_dir,
    normalize_text,
    parse_date,
    safe_filename,
    unique_preserve_order,
)

LOGGER = logging.getLogger(__name__)


class LuxNewsRunner:
    def __init__(self, config: RunConfig, progress_callback: Optional[Callable[[dict], None]] = None):
        self.config = config
        self.progress_callback = progress_callback
        self._wort_login_attempted = False
        self._wort_login_success = False
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
                        status.errors.append(
                            "Contacto login failed. Set CONTACTO_EMAIL and CONTACTO_PASSWORD in .env."
                        )
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
        use_selenium = (
            self.config.search_use_selenium
            or self.config.debug
            or scraper.requires_selenium_search()
        )

        for keyword in self.config.keywords:
            if use_selenium:
                keyword_hits = self._search_with_selenium(
                    scraper, driver, debug_manager, keyword, cutoff_datetime
                )
            else:
                keyword_hits = scraper.search(keyword, cutoff_datetime)
            for hit in keyword_hits:
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

    def _collect_paperjam_hits(
        self,
        scraper: PaperjamMediaScraper,
        driver,
        debug_manager: DebugManager,
        cutoff_datetime: datetime,
    ) -> dict[str, dict]:
        hits_by_url: dict[str, dict] = {}
        urls = scraper.build_search_urls("", search_cutoff=cutoff_datetime)

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

        for payload in hits_by_url.values():
            payload["snippets"] = unique_preserve_order(payload["snippets"])
        return hits_by_url

    def _search_with_selenium(
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
            scraper.prepare_selenium_search_page(driver, keyword, self.config.wait_timeout)
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

    def _process_article(
        self,
        driver,
        debug_manager: DebugManager,
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

        try:
            driver.get(url)
            wait_for_ready(driver, self.config.wait_timeout)
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

            visible_text = self._extract_visible_text_for_media(driver, media_id)
            normalized_text = normalize_text(visible_text)
            matched_keywords = [
                kw for kw in keywords if contains_whole_keyword(normalized_text, kw)
            ]

            if not snippets and visible_text:
                snippet_text = " ".join(visible_text.split())[:200]
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
            try_accept_cookies(driver)
            highlight_keywords_on_page(driver, matched_keywords)
            print_to_pdf(driver, pdf_path)
            stamp_article_pdf_header(pdf_path, media_id, published_at)
            per_article_pdf_path = str(pdf_path)

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

    def _extract_visible_text_for_media(self, driver, media_id: str) -> str:
        if media_id == "paperjam.lu":
            return extract_visible_text_from_selectors(
                driver,
                selectors=[
                    "main article",
                    "article",
                    ".article-content",
                ],
                fallback_to_body=False,
            )
        return extract_visible_text(driver)

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
            except WebDriverException:
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
