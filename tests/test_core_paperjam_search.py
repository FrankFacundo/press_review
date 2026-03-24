from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import luxnews.core as core_module
from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner
from luxnews.models import SearchHit


class _DummyDriver:
    def __init__(self) -> None:
        self.loaded_urls: list[str] = []
        self.page_source = "<html></html>"

    def get(self, url: str) -> None:
        self.loaded_urls.append(url)


class _DummyDebugManager:
    def dump_page(self, *args, **kwargs) -> None:
        return None


def test_collect_paperjam_hits_uses_query_urls_for_each_keyword(monkeypatch) -> None:
    config = RunConfig(
        keywords=["BNP", "ARVAL"],
        medias=["paperjam.lu"],
        max_results=20,
    )
    runner = LuxNewsRunner(config)
    driver = _DummyDriver()
    cutoff = datetime(2026, 3, 24, 11, 0, tzinfo=timezone.utc)
    build_search_calls: list[str] = []

    hit_by_url = {
        "https://paperjam.lu/search?query=BNP&page=1": [
            SearchHit(
                url="https://paperjam.lu/article/bnp-story",
                title="BNP story",
                published_at=cutoff,
                snippet="BNP snippet",
                media_id="paperjam.lu",
            )
        ],
        "https://paperjam.lu/search?query=ARVAL&page=1": [
            SearchHit(
                url="https://paperjam.lu/article/arval-story",
                title="ARVAL story",
                published_at=cutoff,
                snippet="ARVAL snippet",
                media_id="paperjam.lu",
            )
        ],
    }

    scraper = SimpleNamespace(
        definition=SimpleNamespace(
            media_id="paperjam.lu",
            debug_selectors={"search": []},
        ),
        build_search_urls=lambda keyword, search_cutoff=None: _build_urls(keyword, build_search_calls),
        parse_search_results=lambda html, base_url: hit_by_url.get(base_url, []),
        filter_hits_by_date=lambda hits, cutoff_datetime=None: hits,
    )

    def _build_urls(keyword: str, calls: list[str]) -> list[str]:
        calls.append(keyword)
        return [f"https://paperjam.lu/search?query={keyword}&page=1"]

    monkeypatch.setattr(core_module, "wait_for_ready", lambda *_: None)
    monkeypatch.setattr(core_module, "try_accept_cookies", lambda *_: None)
    monkeypatch.setattr(core_module.time, "sleep", lambda *_: None)

    hits = runner._collect_paperjam_hits(
        scraper=scraper,
        driver=driver,
        debug_manager=_DummyDebugManager(),
        cutoff_datetime=cutoff,
    )

    assert build_search_calls == ["BNP", "ARVAL"]
    assert driver.loaded_urls == [
        "https://paperjam.lu/search?query=BNP&page=1",
        "https://paperjam.lu/search?query=ARVAL&page=1",
    ]
    assert hits["https://paperjam.lu/article/bnp-story"]["keywords"] == {"BNP"}
    assert hits["https://paperjam.lu/article/arval-story"]["keywords"] == {"ARVAL"}
