from luxnews.browser_types import BrowserError

from luxnews.config import RunConfig
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.media.virgule import VirguleMediaScraper


class _RecordingDriver:
    def __init__(self):
        self.scripts: list[str] = []

    def execute_script(self, script):
        self.scripts.append(script)


class _FailingDriver:
    def execute_script(self, script):
        raise BrowserError("script failed")


def test_prepare_article_for_pdf_removes_takeover_background_ads():
    scraper = VirguleMediaScraper(
        MEDIA_REGISTRY["virgule.lu"],
        RunConfig(keywords=["k"], medias=["virgule.lu"]),
    )
    driver = _RecordingDriver()

    scraper.prepare_article_for_pdf(driver)

    assert len(driver.scripts) == 1
    script = driver.scripts[0]
    assert "#ad_wallpaper-t1" in script
    assert "#leaderboard-observe-target" in script
    assert "[class*='page-layout_takeoverAdContainer']" in script
    assert "[class*='page-layout_leadingAdContainer']" in script
    assert "[class*='takeover-ad-wallpaper']" in script
    assert "[class*='ad-element_ad']" in script
    assert "background-image: none !important" in script


def test_prepare_article_for_pdf_ignores_browser_errors():
    scraper = VirguleMediaScraper(
        MEDIA_REGISTRY["virgule.lu"],
        RunConfig(keywords=["k"], medias=["virgule.lu"]),
    )

    scraper.prepare_article_for_pdf(_FailingDriver())
