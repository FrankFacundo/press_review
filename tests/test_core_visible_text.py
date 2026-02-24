from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner
import luxnews.core as core_module


def test_extract_visible_text_for_paperjam_uses_article_scope(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["paperjam.lu"]))
    dummy_driver = object()

    def _scoped(driver, selectors, fallback_to_body=True):
        assert driver is dummy_driver
        assert selectors == ["main article", "article", ".article-content"]
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


def test_extract_visible_text_for_other_media_uses_body(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["rtl.lu"]))
    dummy_driver = object()

    scoped_calls = {"count": 0}

    def _scoped(*_):
        scoped_calls["count"] += 1
        return "article text"

    monkeypatch.setattr(core_module, "extract_visible_text_from_selectors", _scoped)
    monkeypatch.setattr(core_module, "extract_visible_text", lambda _: "body text")

    assert runner._extract_visible_text_for_media(dummy_driver, "rtl.lu") == "body text"
    assert scoped_calls["count"] == 0
