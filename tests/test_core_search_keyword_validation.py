from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import luxnews.core as core_module
from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner
from luxnews.models import SearchHit


class _DummyDebugManager:
    def __init__(self) -> None:
        self.dumps: list[dict] = []

    def dump_page(self, *args, **kwargs) -> None:
        self.dumps.append(kwargs)


def test_collect_search_hits_validates_rtl_hit_against_article_keyword(monkeypatch) -> None:
    cutoff = datetime(2026, 4, 28, 11, 0, tzinfo=timezone.utc)
    runner = LuxNewsRunner(RunConfig(keywords=["BNP"], medias=["rtl.lu"]))
    driver = SimpleNamespace()
    hits = [
        SearchHit(
            url="https://rtl.lu/news/national/unrelated",
            title="Unrelated",
            published_at=cutoff,
            media_id="rtl.lu",
        ),
        SearchHit(
            url="https://rtl.lu/news/national/match",
            title="Matching story",
            published_at=cutoff,
            media_id="rtl.lu",
        ),
    ]
    scraper = SimpleNamespace(
        definition=SimpleNamespace(media_id="rtl.lu"),
        requires_selenium_search=lambda: False,
        prefers_plain_search=lambda: True,
        search=lambda keyword, cutoff_datetime=None: hits,
    )
    checked_urls: list[str] = []

    def _matches(*, scraper, driver, debug_manager, hit, keyword) -> bool:
        checked_urls.append(hit.url)
        return hit.url.endswith("/match")

    monkeypatch.setattr(runner, "_search_hit_matches_keyword", _matches)

    result = runner._collect_search_hits(
        scraper=scraper,
        driver=driver,
        debug_manager=_DummyDebugManager(),
        cutoff_datetime=cutoff,
    )

    assert checked_urls == [
        "https://rtl.lu/news/national/unrelated",
        "https://rtl.lu/news/national/match",
    ]
    assert list(result) == ["https://rtl.lu/news/national/match"]
    assert result["https://rtl.lu/news/national/match"]["keywords"] == {"BNP"}


def test_search_hit_matches_keyword_reads_article_visible_text(monkeypatch) -> None:
    runner = LuxNewsRunner(RunConfig(keywords=["BNP PARIBAS"], medias=["rtl.lu"]))
    driver = SimpleNamespace()
    hit = SearchHit(url="https://rtl.lu/news/national/match", title="Matching story")
    scraper = SimpleNamespace(
        definition=SimpleNamespace(media_id="rtl.lu"),
        collect_article_page_urls=lambda driver, url: [url],
    )
    opened_urls: list[str] = []

    def _open_page(driver, url: str) -> None:
        opened_urls.append(url)

    monkeypatch.setattr(runner, "_open_page_best_effort", _open_page)
    monkeypatch.setattr(core_module, "try_accept_cookies", lambda *_: None)
    monkeypatch.setattr(
        runner,
        "_collect_article_visible_texts",
        lambda **_: "The body mentions BNP Paribas in the article.",
    )

    assert runner._search_hit_matches_keyword(
        scraper=scraper,
        driver=driver,
        debug_manager=_DummyDebugManager(),
        hit=hit,
        keyword="BNP PARIBAS",
    )
    assert opened_urls == ["https://rtl.lu/news/national/match"]


def test_search_hit_without_article_keyword_is_rejected(monkeypatch) -> None:
    runner = LuxNewsRunner(RunConfig(keywords=["BNP"], medias=["rtl.lu"]))
    hit = SearchHit(url="https://rtl.lu/news/national/unrelated", title="Unrelated")
    scraper = SimpleNamespace(
        definition=SimpleNamespace(media_id="rtl.lu"),
        collect_article_page_urls=lambda driver, url: [url],
    )

    monkeypatch.setattr(runner, "_open_page_best_effort", lambda *_: None)
    monkeypatch.setattr(core_module, "try_accept_cookies", lambda *_: None)
    monkeypatch.setattr(
        runner,
        "_collect_article_visible_texts",
        lambda **_: "No configured search term appears here.",
    )

    assert not runner._search_hit_matches_keyword(
        scraper=scraper,
        driver=SimpleNamespace(),
        debug_manager=_DummyDebugManager(),
        hit=hit,
        keyword="BNP",
    )
