import json
from pathlib import Path

from luxnews.config import RunConfig
from luxnews.media.factory import build_media_scraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.media.wort import WortMediaScraper


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


def test_factory_uses_wort_scraper():
    config = RunConfig(keywords=["BNP"], medias=["wort.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["wort.lu"], config)
    assert isinstance(scraper, WortMediaScraper)


def test_wort_next_data_search_extraction():
    payload = {
        "props": {
            "pageProps": {
                "data": {
                    "results": [
                        {
                            "href": "/wirtschaft/foo/123456789.html",
                            "title": "Foo title",
                            "published": "2026-02-20T14:35:46.000Z",
                            "intro": [{"fields": [{"name": "intro", "value": "BNP in intro text"}]}],
                        },
                        {
                            "href": "https://www.wort.lu/suche/?q=BNP",
                            "title": "Search page",
                            "published": "2026-02-20T14:35:46.000Z",
                        },
                        {
                            "href": "/wirtschaft/bar/987654321.html",
                            "fields": {"title": "Bar title"},
                            "updated": "2026-02-21T10:00:00.000Z",
                            "teaserIntro": [{"fields": [{"name": "intro", "value": "Second snippet"}]}],
                        },
                    ]
                }
            }
        }
    }
    html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></body></html>"
    )
    config = RunConfig(keywords=["BNP"], medias=["wort.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["wort.lu"], config)

    hits = scraper.parse_search_results(html, "https://www.wort.lu/suche/?q=BNP")

    assert len(hits) == 2
    assert hits[0].url == "https://www.wort.lu/wirtschaft/foo/123456789.html"
    assert hits[0].title == "Foo title"
    assert hits[0].snippet == "BNP in intro text"
    assert hits[0].published_at is not None
    assert hits[0].published_at.date().isoformat() == "2026-02-20"

    assert hits[1].url == "https://www.wort.lu/wirtschaft/bar/987654321.html"
    assert hits[1].title == "Bar title"
    assert hits[1].snippet == "Second snippet"
    assert hits[1].published_at is not None
    assert hits[1].published_at.date().isoformat() == "2026-02-21"
