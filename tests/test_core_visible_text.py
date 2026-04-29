from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner
import luxnews.core as core_module


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


def test_extract_visible_text_for_other_media_uses_body(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["wort.lu"]))
    dummy_driver = object()

    scoped_calls = {"count": 0}

    def _scoped(*_):
        scoped_calls["count"] += 1
        return "article text"

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", _scoped)
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "wort.lu") == "body text"
    assert scoped_calls["count"] == 0
