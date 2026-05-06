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
        requires_browser_search=lambda: False,
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


def test_collect_search_hits_scans_lessentiel_listing_articles_once(monkeypatch) -> None:
    cutoff = datetime(2026, 4, 28, 11, 0, tzinfo=timezone.utc)
    runner = LuxNewsRunner(
        RunConfig(keywords=["BNP PARIBAS", "CARDIF"], medias=["lessentiel.lu"])
    )
    driver = SimpleNamespace()
    hits = [
        SearchHit(
            url="https://www.lessentiel.lu/story/unrelated",
            title="Unrelated",
            published_at=cutoff,
            media_id="lessentiel.lu",
        ),
        SearchHit(
            url="https://www.lessentiel.lu/story/match",
            title="Matching story",
            published_at=cutoff,
            snippet="Listing snippet",
            media_id="lessentiel.lu",
        ),
    ]
    scraper = SimpleNamespace(definition=SimpleNamespace(media_id="lessentiel.lu"))
    scanned_urls: list[str] = []

    def _listing_search(*args, **kwargs):
        assert kwargs["keyword"] == ""
        return hits

    def _article_text(*, scraper, driver, debug_manager, hit) -> str:
        scanned_urls.append(hit.url)
        if hit.url.endswith("/match"):
            return "The article body mentions BNP Paribas."
        return "No configured search term appears here."

    monkeypatch.setattr(runner, "_search_with_browser", _listing_search)
    monkeypatch.setattr(runner, "_collect_search_hit_visible_text", _article_text)

    result = runner._collect_search_hits(
        scraper=scraper,
        driver=driver,
        debug_manager=_DummyDebugManager(),
        cutoff_datetime=cutoff,
    )

    assert scanned_urls == [
        "https://www.lessentiel.lu/story/unrelated",
        "https://www.lessentiel.lu/story/match",
    ]
    assert list(result) == ["https://www.lessentiel.lu/story/match"]
    assert result["https://www.lessentiel.lu/story/match"]["keywords"] == {"BNP PARIBAS"}
    assert result["https://www.lessentiel.lu/story/match"]["snippets"] == ["Listing snippet"]


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
