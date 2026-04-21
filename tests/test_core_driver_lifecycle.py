from __future__ import annotations

from types import SimpleNamespace

import luxnews.core as core_module
from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner
from luxnews.models import ArticleRecord


def _stub_output_writers(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        core_module,
        "build_run_summary_pdf",
        lambda output_path, **kwargs: output_path.write_bytes(b"%PDF-1.4 summary"),
    )
    monkeypatch.setattr(
        core_module,
        "merge_pdfs",
        lambda inputs, output_path: output_path.write_bytes(b"%PDF-1.4 merged"),
    )
    monkeypatch.setattr(
        core_module,
        "dump_json",
        lambda output_path, payload: output_path.write_text("[]", encoding="utf-8"),
    )


def test_run_job_skips_driver_for_plain_search_media_without_hits(monkeypatch, tmp_path) -> None:
    config = RunConfig(
        keywords=["BNP"],
        medias=["tageblatt.lu"],
        output_dir=str(tmp_path),
    )
    runner = LuxNewsRunner(config)
    scraper = SimpleNamespace(
        definition=SimpleNamespace(media_id="tageblatt.lu"),
        requires_selenium_search=lambda: False,
        prefers_plain_search=lambda: True,
    )

    _stub_output_writers(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "_get_scraper", lambda media_id: scraper)
    monkeypatch.setattr(runner, "_collect_search_hits", lambda *args, **kwargs: {})
    monkeypatch.setattr(
        core_module,
        "create_driver",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("create_driver should not be called when no browser work is needed")
        ),
    )

    result = runner.run_job()

    assert result["records"] == []


def test_run_job_creates_driver_only_when_processing_plain_search_hits(monkeypatch, tmp_path) -> None:
    config = RunConfig(
        keywords=["BNP"],
        medias=["tageblatt.lu"],
        output_dir=str(tmp_path),
    )
    runner = LuxNewsRunner(config)
    scraper = SimpleNamespace(
        definition=SimpleNamespace(media_id="tageblatt.lu"),
        requires_selenium_search=lambda: False,
        prefers_plain_search=lambda: True,
    )
    calls: list[str] = []

    class _DummyDriver:
        def quit(self) -> None:
            calls.append("quit")

    driver = _DummyDriver()

    _stub_output_writers(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "_get_scraper", lambda media_id: scraper)

    def _collect_hits(scraper_obj, driver_obj, debug_manager, cutoff_datetime):
        calls.append("collect_hits")
        assert driver_obj is None
        return {
            "https://www.tageblatt.lu/article-1.html": {
                "snippets": ["snippet"],
                "title": "Article title",
                "published_at": None,
            }
        }

    def _process_article(
        driver,
        debug_manager,
        scraper,
        media_id,
        url,
        keywords,
        snippets,
        search_title,
        search_date,
        pdf_dir,
        run_id,
        run_timestamp,
    ):
        calls.append("process_article")
        assert driver is not None
        assert search_title == "Article title"
        return ArticleRecord(
            run_id=run_id,
            run_timestamp=run_timestamp,
            media=media_id,
            url=url,
            title=search_title,
            published_at=None,
            date_unknown=True,
            matched_keywords=["BNP"],
            snippets=snippets,
            per_article_pdf_path=str(tmp_path / "article.pdf"),
            status="ok",
            errors=[],
        )

    monkeypatch.setattr(runner, "_collect_search_hits", _collect_hits)
    monkeypatch.setattr(runner, "_process_article", _process_article)
    monkeypatch.setattr(
        core_module,
        "create_driver",
        lambda *args, **kwargs: calls.append("create_driver") or driver,
    )

    result = runner.run_job()

    assert [step for step in calls if step != "quit"] == [
        "collect_hits",
        "create_driver",
        "process_article",
    ]
    assert calls[-1] == "quit"
    assert len(result["records"]) == 1


def test_run_job_primes_visible_driver_in_headed_mode(monkeypatch, tmp_path) -> None:
    config = RunConfig(
        keywords=["BNP"],
        medias=["tageblatt.lu"],
        output_dir=str(tmp_path),
        headless=False,
    )
    runner = LuxNewsRunner(config)
    scraper = SimpleNamespace(
        definition=SimpleNamespace(media_id="tageblatt.lu"),
        requires_selenium_search=lambda: False,
        prefers_plain_search=lambda: True,
    )
    loaded_urls: list[str] = []

    class _DummyDriver:
        current_url = "about:blank"

        def get(self, url: str) -> None:
            loaded_urls.append(url)
            self.current_url = url

        def quit(self) -> None:
            loaded_urls.append("quit")

    _stub_output_writers(monkeypatch, tmp_path)
    monkeypatch.setattr(runner, "_get_scraper", lambda media_id: scraper)
    monkeypatch.setattr(runner, "_collect_search_hits", lambda *args, **kwargs: {})
    monkeypatch.setattr(core_module, "create_driver", lambda *args, **kwargs: _DummyDriver())

    runner.run_job()

    assert loaded_urls
    assert loaded_urls[0].startswith("data:text/html;charset=utf-8,")
    assert "quit" in loaded_urls
