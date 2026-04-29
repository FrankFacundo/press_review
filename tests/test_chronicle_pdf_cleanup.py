from luxnews.browser_types import BrowserError

from luxnews.config import RunConfig
from luxnews.media.chronicle import ChronicleMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY


class _RecordingDriver:
    def __init__(self):
        self.scripts: list[str] = []

    def execute_script(self, script):
        self.scripts.append(script)


class _FailingDriver:
    def execute_script(self, script):
        raise BrowserError("script failed")


def test_prepare_article_for_pdf_isolates_chronicle_article_content():
    scraper = ChronicleMediaScraper(
        MEDIA_REGISTRY["chronicle.lu"],
        RunConfig(keywords=["k"], medias=["chronicle.lu"]),
    )
    driver = _RecordingDriver()

    scraper.prepare_article_for_pdf(driver)

    assert len(driver.scripts) == 1
    script = driver.scripts[0]
    assert "@page { margin: 42px 24px 24px 24px; }" in script
    assert "ol.breadcrumb" in script
    assert ".well.related-news" in script
    assert ".widget.latest-news" in script
    assert "child !== articleWrap" in script
    assert ".article-meta .pull-left" in script
    assert ".article-meta .pull-right" in script


def test_prepare_article_for_pdf_ignores_browser_errors():
    scraper = ChronicleMediaScraper(
        MEDIA_REGISTRY["chronicle.lu"],
        RunConfig(keywords=["k"], medias=["chronicle.lu"]),
    )

    scraper.prepare_article_for_pdf(_FailingDriver())
