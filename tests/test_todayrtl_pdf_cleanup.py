from selenium.common.exceptions import WebDriverException

from luxnews.config import RunConfig
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.media.todayrtl import TodayRTLMediaScraper


class _RecordingDriver:
    def __init__(self):
        self.scripts: list[str] = []

    def execute_script(self, script):
        self.scripts.append(script)


class _FailingDriver:
    def execute_script(self, script):
        raise WebDriverException("script failed")


def test_prepare_article_for_pdf_hides_notification_overlays():
    scraper = TodayRTLMediaScraper(
        MEDIA_REGISTRY["today.rtl.lu"],
        RunConfig(keywords=["k"], medias=["today.rtl.lu"]),
    )
    driver = _RecordingDriver()

    scraper.prepare_article_for_pdf(driver)

    assert len(driver.scripts) == 1
    script = driver.scripts[0]
    assert "#onesignal-slidedown-container" in script
    assert "notifications" in script
    assert "modal-backdrop" in script


def test_prepare_article_for_pdf_ignores_webdriver_errors():
    scraper = TodayRTLMediaScraper(
        MEDIA_REGISTRY["today.rtl.lu"],
        RunConfig(keywords=["k"], medias=["today.rtl.lu"]),
    )

    scraper.prepare_article_for_pdf(_FailingDriver())
