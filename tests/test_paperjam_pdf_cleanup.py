from luxnews.browser_types import BrowserError

from luxnews.config import RunConfig
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY


class _RecordingDriver:
    def __init__(self):
        self.scripts: list[str] = []

    def execute_script(self, script):
        self.scripts.append(script)


class _FailingDriver:
    def execute_script(self, script):
        raise BrowserError("script failed")


def test_prepare_article_for_pdf_hides_onesignal_prompt():
    scraper = PaperjamMediaScraper(
        MEDIA_REGISTRY["paperjam.lu"],
        RunConfig(keywords=["k"], medias=["paperjam.lu"]),
    )
    driver = _RecordingDriver()

    scraper.prepare_article_for_pdf(driver)

    assert len(driver.scripts) == 1
    script = driver.scripts[0]
    assert "#onesignal-slidedown-container" in script
    assert "#onesignal-slidedown-dialog" in script
    assert "#onesignal-slidedown-allow-button" in script
    assert ".top-read-block" in script
    assert ".article-footer__associated" in script


def test_prepare_article_for_pdf_ignores_browser_errors():
    scraper = PaperjamMediaScraper(
        MEDIA_REGISTRY["paperjam.lu"],
        RunConfig(keywords=["k"], medias=["paperjam.lu"]),
    )

    scraper.prepare_article_for_pdf(_FailingDriver())
