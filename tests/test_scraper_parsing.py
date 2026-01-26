from pathlib import Path

from luxnews.config import RunConfig
from luxnews.media.base import BaseMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY


def test_parse_search_results_fixture():
    html_path = Path(__file__).parent / "fixtures" / "search_fixture.html"
    html = html_path.read_text(encoding="utf-8")
    config = RunConfig(keywords=["BNP"], medias=["rtl.lu"])
    scraper = BaseMediaScraper(MEDIA_REGISTRY["rtl.lu"], config)

    hits = scraper.parse_search_results(html, "https://rtl.lu/search?q=BNP")
    urls = [hit.url for hit in hits]

    assert "https://rtl.lu/news/article-1" in urls
    assert "https://rtl.lu/news/article-2" in urls
