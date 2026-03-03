from selenium.common.exceptions import WebDriverException

from luxnews.config import RunConfig
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.media.reporter import ReporterMediaScraper


class _RecordingDriver:
    def __init__(self):
        self.scripts: list[str] = []

    def execute_script(self, script):
        self.scripts.append(script)


class _FailingDriver:
    def execute_script(self, script):
        raise WebDriverException("script failed")


def test_prepare_article_for_pdf_hides_cookiebot_dialog():
    scraper = ReporterMediaScraper(
        MEDIA_REGISTRY["reporter.lu"],
        RunConfig(keywords=["k"], medias=["reporter.lu"]),
    )
    driver = _RecordingDriver()

    scraper.prepare_article_for_pdf(driver)

    assert len(driver.scripts) == 1
    script = driver.scripts[0]
    assert "#CybotCookiebotDialog" in script
    assert "#CybotCookiebotDialogBodyUnderlay" in script
    assert "alle zulassen" in script


def test_prepare_article_for_pdf_ignores_webdriver_errors():
    scraper = ReporterMediaScraper(
        MEDIA_REGISTRY["reporter.lu"],
        RunConfig(keywords=["k"], medias=["reporter.lu"]),
    )

    scraper.prepare_article_for_pdf(_FailingDriver())
