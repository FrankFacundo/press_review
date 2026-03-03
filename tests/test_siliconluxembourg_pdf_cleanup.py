from selenium.common.exceptions import WebDriverException

from luxnews.config import RunConfig
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.media.siliconluxembourg import SiliconLuxembourgMediaScraper


class _RecordingDriver:
    def __init__(self):
        self.scripts: list[str] = []

    def execute_script(self, script):
        self.scripts.append(script)


class _FailingDriver:
    def execute_script(self, script):
        raise WebDriverException("script failed")


def test_prepare_article_for_pdf_hides_top_billboard_ad():
    scraper = SiliconLuxembourgMediaScraper(
        MEDIA_REGISTRY["siliconluxembourg.lu"],
        RunConfig(keywords=["k"], medias=["siliconluxembourg.lu"]),
    )
    driver = _RecordingDriver()

    scraper.prepare_article_for_pdf(driver)

    assert len(driver.scripts) == 1
    script = driver.scripts[0]
    assert ".cs-custom-content-header-after" in script
    assert "a[aria-label='banner-billboard']" in script
    assert "img[alt='banner-billboard']" in script


def test_prepare_article_for_pdf_ignores_webdriver_errors():
    scraper = SiliconLuxembourgMediaScraper(
        MEDIA_REGISTRY["siliconluxembourg.lu"],
        RunConfig(keywords=["k"], medias=["siliconluxembourg.lu"]),
    )

    scraper.prepare_article_for_pdf(_FailingDriver())
