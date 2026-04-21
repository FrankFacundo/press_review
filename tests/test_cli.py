from datetime import datetime, timezone

from typer.testing import CliRunner

from luxnews.cli import app
from luxnews.models import SearchHit


runner = CliRunner()


def test_debug_search_skips_driver_for_plain_search_scrapers(monkeypatch):
    class FakeScraper:
        def requires_selenium_search(self) -> bool:
            return False

        def prefers_plain_search(self) -> bool:
            return True

        def search(self, keyword: str, cutoff_datetime=None) -> list[SearchHit]:
            assert keyword == "BNP"
            assert cutoff_datetime is not None
            return [
                SearchHit(
                    url="https://www.tageblatt.lu/Wirtschaft/result-1.html",
                    title="BNP result",
                    published_at=datetime(2026, 4, 20, 8, 0, tzinfo=timezone.utc),
                    snippet="BNP result snippet",
                    media_id="tageblatt.lu",
                )
            ]

    class FakeRunner:
        def __init__(self, cfg):
            self.cfg = cfg

        def _search_requires_browser(self, scraper) -> bool:
            return False

        def _search_with_selenium(self, *args, **kwargs):
            raise AssertionError("Selenium search should not be used for plain-search scrapers")

    monkeypatch.setattr("luxnews.cli.build_media_scraper", lambda definition, cfg: FakeScraper())
    monkeypatch.setattr("luxnews.cli.LuxNewsRunner", FakeRunner)
    monkeypatch.setattr(
        "luxnews.cli.create_driver",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("create_driver should not be called for plain-search scrapers")
        ),
    )

    result = runner.invoke(
        app,
        [
            "debug-search",
            "--media",
            "tageblatt.lu",
            "--keyword",
            "BNP",
        ],
    )

    assert result.exit_code == 0
    assert "Found 1 hits for BNP on tageblatt.lu" in result.stdout
    assert "https://www.tageblatt.lu/Wirtschaft/result-1.html | BNP result" in result.stdout
