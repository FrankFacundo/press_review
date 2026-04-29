from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner
import luxnews.core as core_module

from bs4 import BeautifulSoup


class _SelectorTextDriver:
    def __init__(self, html: str):
        self.soup = BeautifulSoup(html, "lxml")

    def execute_script(self, script, selectors, fallback_to_body):
        for selector in selectors:
            node = self.soup.select_one(selector)
            if not node:
                continue
            text = " ".join(node.get_text(" ", strip=True).split())
            if text:
                return text
        if fallback_to_body:
            body = self.soup.select_one("body")
            return " ".join(body.get_text(" ", strip=True).split()) if body else ""
        return ""


class _SiliconArticleTextDriver:
    def __init__(self, html: str):
        self.soup = BeautifulSoup(html, "lxml")
        self.calls: list[tuple[list[str], list[str]]] = []

    def execute_script(self, script, selectors, remove_selectors):
        self.calls.append((selectors, remove_selectors))
        parts: list[str] = []
        for selector in selectors:
            node = self.soup.select_one(selector)
            if not node:
                continue
            clone_soup = BeautifulSoup(str(node), "lxml")
            clone = clone_soup.find(node.name)
            if not clone:
                continue
            for remove_selector in remove_selectors:
                for removed in clone.select(remove_selector):
                    removed.decompose()
            text = " ".join(clone.get_text(" ", strip=True).split())
            if text:
                parts.append(text)
        return " ".join(parts)


def test_extract_visible_text_for_paperjam_uses_article_scope(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["paperjam.lu"]))
    dummy_driver = object()

    def _scoped(driver, selectors, fallback_to_body=True):
        assert driver is dummy_driver
        assert selectors == [
            "main article .article-content",
            "article .article-content",
            ".article-content",
            "main article",
            "article",
        ]
        assert fallback_to_body is False
        return "article text"

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", _scoped)
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "paperjam.lu") == "article text"


def test_extract_visible_text_for_paperjam_does_not_fallback_to_body(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["paperjam.lu"]))
    dummy_driver = object()

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", lambda *_, **__: "")
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "paperjam.lu") == ""


def test_extract_visible_text_for_lequotidien_uses_article_scope(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["lequotidien.lu"]))
    dummy_driver = object()

    def _scoped(driver, selectors, fallback_to_body=True):
        assert driver is dummy_driver
        assert selectors == [
            "#main-content .content article.post-listing .entry",
            "article.post-listing .entry",
            ".post-listing .entry",
        ]
        assert fallback_to_body is False
        return "article text"

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", _scoped)
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "lequotidien.lu") == "article text"


def test_extract_visible_text_for_lequotidien_does_not_fallback_to_body(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["lequotidien.lu"]))
    dummy_driver = object()

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", lambda *_, **__: "")
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "lequotidien.lu") == ""


def test_extract_visible_text_for_contacto_uses_article_scope(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["contacto.lu"]))
    dummy_driver = object()

    def _scoped(driver, selectors, fallback_to_body=True):
        assert driver is dummy_driver
        assert selectors == [
            "article section[data-testid='article-body']",
            "section[data-testid='article-body']",
        ]
        assert fallback_to_body is False
        return "article text"

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", _scoped)
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "contacto.lu") == "article text"


def test_extract_visible_text_for_contacto_does_not_fallback_to_body(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["contacto.lu"]))
    dummy_driver = object()

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", lambda *_, **__: "")
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "contacto.lu") == ""


def test_extract_visible_text_for_chronicle_uses_article_scope(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["chronicle.lu"]))
    dummy_driver = object()

    def _scoped(driver, selectors, fallback_to_body=True):
        assert driver is dummy_driver
        assert selectors == [
            ".article-wrap article.article",
            "article.article",
            ".article-wrap",
        ]
        assert fallback_to_body is False
        return "article text"

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", _scoped)
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "chronicle.lu") == "article text"


def test_extract_visible_text_for_chronicle_does_not_fallback_to_body(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["chronicle.lu"]))
    dummy_driver = object()

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", lambda *_, **__: "")
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text with related news")

    assert runner._extract_visible_text_for_media(dummy_driver, "chronicle.lu") == ""


def test_extract_visible_text_for_chronicle_excludes_related_news():
    runner = LuxNewsRunner(RunConfig(keywords=["BNP PARIBAS"], medias=["chronicle.lu"]))
    driver = _SelectorTextDriver(
        """
        <body>
          <div class="article-wrap">
            <article class="article">
              <h1>State Street to Launch Tokenised Fund Servicing from Luxembourg</h1>
              <div class="article-body">
                <p>State Street announced a Luxembourg fund servicing launch.</p>
              </div>
            </article>
          </div>
          <div class="well related-news">
            <h4>Related News</h4>
            <a href="/category/jobs-appointments/60388-bgl-bnp-paribas-announces-executive-appointments">
              BGL BNP Paribas Announces Executive Appointments
            </a>
          </div>
        </body>
        """
    )

    text = runner._extract_visible_text_for_media(driver, "chronicle.lu")

    assert "State Street" in text
    assert "BNP Paribas" not in text
    assert "Related News" not in text


def test_extract_visible_text_for_siliconluxembourg_excludes_page_chrome():
    runner = LuxNewsRunner(RunConfig(keywords=["MICROLUX"], medias=["siliconluxembourg.lu"]))
    driver = _SiliconArticleTextDriver(
        """
        <body>
          <header>Microlux in navigation</header>
          <main id="main">
            <div id="content">
              <div id="primary">
                <div class="cs-entry__header-info">
                  <h1>Foyer And taxx.lu Announce Partnership To Simplify Tax Filing</h1>
                  <div class="cs-entry__share-buttons">Microlux share widget</div>
                </div>
                <div class="entry-content">
                  <p>Foyer and taxx.lu join forces in Luxembourg.</p>
                  <div class="mailmunch-forms-after-post">Microlux signup widget</div>
                </div>
                <div class="cs-entry__tags">Microlux tag outside the article body</div>
              </div>
            </div>
            <aside id="secondary">Microlux upcoming event</aside>
          </main>
          <div class="cs-entry__post-related">Microlux related post</div>
        </body>
        """
    )

    text = runner._extract_visible_text_for_media(driver, "siliconluxembourg.lu")

    assert "Foyer And taxx.lu" in text
    assert "join forces in Luxembourg" in text
    assert "Microlux" not in text
    assert driver.calls == [
        (
            [
                "#primary .cs-entry__header-info",
                "#primary .entry-content",
            ],
            [
                ".cs-entry__share-buttons",
                ".cs-entry__metabar",
                ".cs-entry__tags",
                ".cs-entry__after-share-buttons",
                ".cs-entry__author",
                ".cs-entry__subscribe",
                ".pk-share-buttons-wrap",
                "[class*='mailmunch-forms']",
                "script",
                "style",
                "noscript",
            ],
        )
    ]


def test_extract_visible_text_for_siliconluxembourg_does_not_fallback_to_body():
    runner = LuxNewsRunner(RunConfig(keywords=["MICROLUX"], medias=["siliconluxembourg.lu"]))
    driver = _SiliconArticleTextDriver(
        """
        <body>
          <header>Microlux in navigation</header>
          <aside>Microlux in sidebar</aside>
        </body>
        """
    )

    assert runner._extract_visible_text_for_media(driver, "siliconluxembourg.lu") == ""


def test_extract_visible_text_for_wort_uses_article_scope(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["wort.lu"]))
    dummy_driver = object()

    def _scoped(driver, selectors, fallback_to_body=True):
        assert driver is dummy_driver
        assert selectors == [
            "main[class*='article-two-thirds-layout_articleTwoThirdsLayout'] > article",
            "main > article[lang]",
            "main > article",
        ]
        assert fallback_to_body is False
        return "article text"

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", _scoped)
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "wort.lu") == "article text"


def test_extract_visible_text_for_wort_excludes_page_chrome():
    runner = LuxNewsRunner(RunConfig(keywords=["BNP PARIBAS"], medias=["wort.lu"]))
    driver = _SelectorTextDriver(
        """
        <body>
          <main class="article-two-thirds-layout_articleTwoThirdsLayout__6ddXE">
            <article lang="de" class="article-two-thirds-layout_article__DHdd1">
              <h1>Stefano Bensi kehrt an alte Wirkungsstätte zurück</h1>
              <p>Was passiert im Luxemburger Fußball?</p>
              <div class="tik4-rich-text">
                <p>Rumelange will unter dem neuen Trainer eine gute Saison spielen.</p>
              </div>
            </article>
            <aside>
              <article>
                <h2>BGL BNP Paribas Announces Executive Appointments</h2>
              </article>
            </aside>
          </main>
          <section id="recirculation">
            <article>
              <h2>BNP Paribas outside the article body</h2>
            </article>
          </section>
        </body>
        """
    )

    text = runner._extract_visible_text_for_media(driver, "wort.lu")

    assert "Stefano Bensi" in text
    assert "Rumelange" in text
    assert "BNP Paribas" not in text


def test_extract_visible_text_for_wort_does_not_fallback_to_body(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["wort.lu"]))
    dummy_driver = object()

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", lambda *_, **__: "")
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "wort.lu") == ""


def test_extract_visible_text_for_other_media_uses_body(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["infogreen.lu"]))
    dummy_driver = object()

    scoped_calls = {"count": 0}

    def _scoped(*_):
        scoped_calls["count"] += 1
        return "article text"

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", _scoped)
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "infogreen.lu") == "body text"
    assert scoped_calls["count"] == 0
