from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import luxnews.core as core_module
from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner


class _DummyDriver:
    def __init__(self) -> None:
        self.current_url = ""
        self.page_source = "<html></html>"


class _DummyDebugManager:
    def dump_page(self, *args, **kwargs) -> None:
        return None


def test_process_article_checks_all_paperjam_pages_for_keywords(monkeypatch, tmp_path) -> None:
    article_url = "https://paperjam.lu/article/citco-transfere"
    second_page_url = f"{article_url}?page=2"
    visible_text_by_url = {
        article_url: "First page without the keyword.",
        second_page_url: "Second page mentions BNP Paribas in the body.",
    }
    visited_urls: list[str] = []
    printed_urls: list[str] = []
    merged_inputs: list[str] = []

    runner = LuxNewsRunner(RunConfig(keywords=["BNP"], medias=["paperjam.lu"]))
    driver = _DummyDriver()
    scraper = SimpleNamespace(
        prepare_article_for_pdf=lambda *_: None,
        collect_article_page_urls=lambda *_: [article_url, second_page_url],
    )

    def _open_page(driver_obj, url: str) -> None:
        visited_urls.append(url)
        driver_obj.current_url = url
        driver_obj.page_source = f"<html><body>{url}</body></html>"

    def _print_to_pdf(driver_obj, output_path) -> None:
        printed_urls.append(driver_obj.current_url)
        output_path.write_bytes(b"%PDF-1.4")

    def _merge_pdfs(inputs, output_path) -> None:
        merged_inputs.extend(str(path) for path in inputs)
        output_path.write_bytes(b"%PDF-1.4 merged")

    monkeypatch.setattr(runner, "_open_page_best_effort", _open_page)
    monkeypatch.setattr(core_module, "try_accept_cookies", lambda *_: None)
    monkeypatch.setattr(core_module, "extract_title", lambda *_: "Paperjam story")
    monkeypatch.setattr(runner, "_extract_date", lambda *_: None)
    monkeypatch.setattr(
        runner,
        "_extract_visible_text_for_media",
        lambda driver_obj, media_id: visible_text_by_url[driver_obj.current_url],
    )
    monkeypatch.setattr(core_module, "highlight_keywords_on_page", lambda *_: 1)
    monkeypatch.setattr(core_module, "print_to_pdf", _print_to_pdf)
    monkeypatch.setattr(core_module, "merge_pdfs", _merge_pdfs)
    monkeypatch.setattr(core_module, "stamp_article_pdf_header", lambda *_: None)

    record = runner._process_article(
        driver=driver,
        debug_manager=_DummyDebugManager(),
        scraper=scraper,
        media_id="paperjam.lu",
        url=article_url,
        keywords=["BNP"],
        snippets=[],
        search_title="Paperjam story",
        search_date=datetime(2026, 3, 24, 12, 0, tzinfo=timezone.utc),
        pdf_dir=tmp_path,
        run_id="run_1",
        run_timestamp="2026-03-24T12:00:00+00:00",
    )

    assert record.status == "ok"
    assert record.matched_keywords == ["BNP"]
    assert visited_urls == [article_url, second_page_url, article_url, second_page_url]
    assert printed_urls == [article_url, second_page_url]
    assert len(merged_inputs) == 2
    assert record.per_article_pdf_path is not None
    assert "Second page mentions BNP Paribas" in " ".join(record.snippets)
