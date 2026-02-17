from pathlib import Path

from luxnews.config import RunConfig
from luxnews.media.factory import build_media_scraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY


def test_parse_search_results_fixture():
    html_path = Path(__file__).parent / "fixtures" / "search_fixture.html"
    html = html_path.read_text(encoding="utf-8")
    config = RunConfig(keywords=["BNP"], medias=["rtl.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["rtl.lu"], config)

    hits = scraper.parse_search_results(html, "https://rtl.lu/search?q=BNP")
    urls = [hit.url for hit in hits]

    assert "https://rtl.lu/news/article-1" in urls
    assert "https://rtl.lu/news/article-2" in urls


def test_rtl_search_date_class_extraction():
    html = """
    <article>
      <h2><a href="https://rtl.lu/news/article-1">Article One</a></h2>
      <a class="rtl-search-res_date">04.02.2026</a>
    </article>
    """
    config = RunConfig(keywords=["BNP"], medias=["rtl.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["rtl.lu"], config)

    hits = scraper.parse_search_results(html, "https://rtl.lu/search?q=BNP")

    assert len(hits) == 1
    assert hits[0].published_at is not None
    assert hits[0].published_at.date().isoformat() == "2026-02-04"


def test_factory_uses_paperjam_scraper():
    config = RunConfig(keywords=["BNP"], medias=["paperjam.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["paperjam.lu"], config)
    assert isinstance(scraper, PaperjamMediaScraper)
    assert scraper.requires_selenium_search() is True


def test_paperjam_search_card_extraction():
    html = """
    <div class="search_results-item">
      <a href="/article/banques"><h4 class="news-card__title" title="Banques">Banques</h4></a>
      <div class="informations">News • 04.02.2026</div>
      <p>BNP Paribas publishes Q4 results.</p>
    </div>
    """
    config = RunConfig(keywords=["BNP"], medias=["paperjam.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["paperjam.lu"], config)

    hits = scraper.parse_search_results(html, "https://paperjam.lu/search?query=BNP&page=1")

    assert len(hits) == 1
    assert hits[0].url == "https://paperjam.lu/article/banques"
    assert hits[0].title == "Banques"
    assert hits[0].snippet == "BNP Paribas publishes Q4 results."
    assert hits[0].published_at is not None
    assert hits[0].published_at.date().isoformat() == "2026-02-04"
