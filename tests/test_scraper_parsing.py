import json
from datetime import datetime, timezone
from pathlib import Path

from luxnews.config import RunConfig
from luxnews.media.delano import DelanoMediaScraper
from luxnews.media.factory import build_media_scraper
from luxnews.media.lessentiel import LessentielMediaScraper
from luxnews.media.luxtimes import LuxTimesMediaScraper
from luxnews.media.paperjam import PaperjamMediaScraper
from luxnews.media.registry import MEDIA_REGISTRY
from luxnews.media.virgule import VirguleMediaScraper
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


def test_paperjam_build_search_urls_contains_pagination_to_page_8():
    config = RunConfig(keywords=["BNP"], medias=["paperjam.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["paperjam.lu"], config)

    urls = scraper.build_search_urls("ignored")

    assert len(urls) == 8
    assert urls[0].startswith(
        "https://paperjam.lu/search?numericRefinementList%5BpublicationDate%5D="
    )
    assert urls[1].endswith("&page=2")
    assert urls[7].endswith("&page=8")


def test_paperjam_publication_filter_mapping():
    config = RunConfig(keywords=["BNP"], medias=["paperjam.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["paperjam.lu"], config)

    now = datetime(2026, 2, 24, 15, 0, tzinfo=timezone.utc)  # Tuesday
    assert (
        scraper.resolve_publication_filter(
            search_cutoff=datetime(2026, 2, 24, 11, 0, tzinfo=timezone.utc),
            now=now,
        )
        == "Aujourd'hui"
    )
    assert (
        scraper.resolve_publication_filter(
            search_cutoff=datetime(2026, 2, 23, 11, 0, tzinfo=timezone.utc),
            now=now,
        )
        == "Depuis hier"
    )
    assert (
        scraper.resolve_publication_filter(
            search_cutoff=datetime(2026, 2, 20, 11, 0, tzinfo=timezone.utc),
            now=datetime(2026, 2, 23, 9, 0, tzinfo=timezone.utc),  # Monday
        )
        == "Depuis une semaine"
    )


def test_factory_uses_wort_scraper():
    config = RunConfig(keywords=["BNP"], medias=["wort.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["wort.lu"], config)
    assert isinstance(scraper, WortMediaScraper)


def test_factory_uses_virgule_scraper():
    config = RunConfig(keywords=["BNP"], medias=["virgule.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["virgule.lu"], config)
    assert isinstance(scraper, VirguleMediaScraper)
    assert scraper.requires_selenium_search() is True


def test_factory_uses_luxtimes_scraper_and_alias():
    config = RunConfig(keywords=["BNP"], medias=["luxtimes.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["luxtimes.lu"], config)
    assert isinstance(scraper, LuxTimesMediaScraper)

    alias_scraper = build_media_scraper(MEDIA_REGISTRY["luxtimes.lu/en"], config)
    assert isinstance(alias_scraper, LuxTimesMediaScraper)


def test_factory_uses_delano_scraper():
    config = RunConfig(keywords=["BNP"], medias=["delano.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["delano.lu"], config)
    assert isinstance(scraper, DelanoMediaScraper)
    assert scraper.requires_selenium_search() is True


def test_factory_uses_lessentiel_scraper_and_alias():
    config = RunConfig(keywords=["BNP"], medias=["lessentiel.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["lessentiel.lu"], config)
    assert isinstance(scraper, LessentielMediaScraper)
    assert scraper.requires_selenium_search() is True

    alias_scraper = build_media_scraper(MEDIA_REGISTRY["lessentiel.lu/fr"], config)
    assert isinstance(alias_scraper, LessentielMediaScraper)


def test_virgule_search_card_extraction_ignores_navigation_links():
    html = """
    <main>
      <article class="DefaultTeaser_default-teaser__6PRXv">
        <a class="DefaultTeaser_default-teaser__link__n6gg6" href="/international/example-article/138260174.html">
          <span class="TeaserTaxonomy_teaser-taxonomy__label__A6YFz">En mer du Nord</span>
          <span class="TeaserContent_teaser-content__title__title___hKXk">
            La Belgique a intercepté un pétrolier de la «flotte fantôme» russe
          </span>
          <p class="TeaserContent_teaser-content__introduction__zUyr8">
            Les forces spéciales belges ont intercepté un navire russe.
          </p>
          <time class="DateTime_date-time__oPWZl TeaserContent_teaser-content__date-time___PVRb">
            01/03/2026
          </time>
        </a>
      </article>
      <a class="navigation-link_navigationLink__whSNA" href="/services/jeux/sudoku/696.html">Sudoku</a>
    </main>
    """
    config = RunConfig(keywords=["finance"], medias=["virgule.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["virgule.lu"], config)

    hits = scraper.parse_search_results(html, "https://www.virgule.lu/recherche/?q=finance")

    assert len(hits) == 1
    assert (
        hits[0].url
        == "https://www.virgule.lu/international/example-article/138260174.html"
    )
    assert hits[0].title == "La Belgique a intercepté un pétrolier de la «flotte fantôme» russe"
    assert hits[0].snippet == "Les forces spéciales belges ont intercepté un navire russe."
    assert hits[0].published_at is not None
    assert hits[0].published_at.date().isoformat() == "2026-03-01"


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


def test_luxtimes_next_data_search_extraction():
    payload = {
        "props": {
            "pageProps": {
                "data": {
                    "results": [
                        {
                            "href": "https://www.luxtimes.lu/businessandfinance/example-1/138306649.html",
                            "title": "Luxembourg finance article",
                            "published": "2026-03-02T11:40:00.000Z",
                            "intro": [{"fields": [{"name": "intro", "value": "Finance summary"}]}],
                        },
                        {
                            "href": "/search/?q=finance",
                            "title": "Search page",
                            "published": "2026-03-02T11:00:00.000Z",
                        },
                        {
                            "href": "/luxembourg/example-2/137021055.html",
                            "title": "Second article",
                            "updated": "2026-03-01T10:00:00.000Z",
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
    config = RunConfig(keywords=["finance"], medias=["luxtimes.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["luxtimes.lu"], config)

    hits = scraper.parse_search_results(html, "https://www.luxtimes.lu/search/?q=finance")

    assert len(hits) == 2
    assert hits[0].url == "https://www.luxtimes.lu/businessandfinance/example-1/138306649.html"
    assert hits[0].title == "Luxembourg finance article"
    assert hits[0].snippet == "Finance summary"
    assert hits[0].published_at is not None
    assert hits[0].published_at.date().isoformat() == "2026-03-02"

    assert hits[1].url == "https://www.luxtimes.lu/luxembourg/example-2/137021055.html"
    assert hits[1].title == "Second article"
    assert hits[1].snippet == "Second snippet"
    assert hits[1].published_at is not None
    assert hits[1].published_at.date().isoformat() == "2026-03-01"


def test_delano_search_card_extraction_ignores_navigation():
    html = """
    <main>
      <div class="sectors-menu__col">
        <a href="https://delano.lu/article/menu-link-should-be-ignored">
          INSTITUTIONS Paul Yon appointed director general of MSF Luxembourg
        </a>
      </div>
      <div class="search__results-item col-sm-6 col-xs-12">
        <a href="https://delano.lu/article/allfunds-partners-with-waystone-for-manco-services">
          <div class="news-card">
            <h4 class="news-card__title" title="Allfunds partners with Waystone for ManCo services">
              Allfunds partners with Waystone for ManCo services
            </h4>
            <div class="informations">Emilio Naud • Monday 02.03.2026</div>
          </div>
        </a>
      </div>
    </main>
    """
    config = RunConfig(keywords=["finance"], medias=["delano.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["delano.lu"], config)

    hits = scraper.parse_search_results(html, "https://delano.lu/search?query=finance")

    assert len(hits) == 1
    assert (
        hits[0].url
        == "https://delano.lu/article/allfunds-partners-with-waystone-for-manco-services"
    )
    assert hits[0].title == "Allfunds partners with Waystone for ManCo services"
    assert hits[0].published_at is not None
    assert hits[0].published_at.date().isoformat() == "2026-03-02"


def test_lessentiel_next_data_search_extraction():
    payload = {
        "props": {
            "pageProps": {
                "store": {
                    "pageData": {
                        "data": {
                            "teasers": [
                                {
                                    "url": "/story/au-luxembourg-une-mule-financiere-103512602",
                                    "title": "Une mule financière interpellée",
                                    "lead": "Une interpellation a eu lieu à Luxembourg.",
                                    "published": "2026-02-24T10:00:12.151Z",
                                },
                                {
                                    "url": "/fr",
                                    "title": "Homepage",
                                    "published": "2026-02-24T10:00:12.151Z",
                                },
                                {
                                    "url": "https://lessentiel.lu/story/deuxieme-resultat-103515106",
                                    "titleHeader": "Deuxième résultat",
                                    "updated": "2026-02-28T07:13:50.551Z",
                                },
                            ]
                        }
                    }
                }
            }
        }
    }
    html = (
        '<html><body><script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}"
        "</script></body></html>"
    )
    config = RunConfig(keywords=["finance"], medias=["lessentiel.lu"])
    scraper = build_media_scraper(MEDIA_REGISTRY["lessentiel.lu"], config)

    hits = scraper.parse_search_results(html, "https://lessentiel.lu/fr/search?q=finance")

    assert len(hits) == 2
    assert hits[0].url == "https://lessentiel.lu/story/au-luxembourg-une-mule-financiere-103512602"
    assert hits[0].title == "Une mule financière interpellée"
    assert hits[0].snippet == "Une interpellation a eu lieu à Luxembourg."
    assert hits[0].published_at is not None
    assert hits[0].published_at.date().isoformat() == "2026-02-24"

    assert hits[1].url == "https://lessentiel.lu/story/deuxieme-resultat-103515106"
    assert hits[1].title == "Deuxième résultat"
    assert hits[1].snippet is None
    assert hits[1].published_at is not None
    assert hits[1].published_at.date().isoformat() == "2026-02-28"
