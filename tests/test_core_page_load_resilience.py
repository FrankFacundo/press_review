import pytest
from selenium.common.exceptions import TimeoutException, WebDriverException

from luxnews.config import RunConfig
from luxnews.core import LuxNewsRunner
import luxnews.core as core_module


class _DummyDriver:
    def __init__(self, get_exc: Exception | None = None):
        self.get_exc = get_exc
        self.loaded_urls: list[str] = []
        self.script_calls: list[str] = []

    def get(self, url: str) -> None:
        self.loaded_urls.append(url)
        if self.get_exc:
            raise self.get_exc

    def execute_script(self, script: str):
        self.script_calls.append(script)
        return None


def test_open_page_best_effort_stops_load_on_wait_timeout(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["rtl.lu"]))
    driver = _DummyDriver()

    def _raise_timeout(*_):
        raise TimeoutException("timeout")

    monkeypatch.setattr(core_module, "wait_for_ready", _raise_timeout)

    runner._open_page_best_effort(driver, "https://example.com")

    assert driver.loaded_urls == ["https://example.com"]
    assert driver.script_calls == ["window.stop();"]


def test_open_page_best_effort_stops_load_on_renderer_timeout(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["rtl.lu"]))
    driver = _DummyDriver(get_exc=WebDriverException("Timed out receiving message from renderer"))

    wait_called = {"count": 0}

    def _wait(*_):
        wait_called["count"] += 1

    monkeypatch.setattr(core_module, "wait_for_ready", _wait)

    runner._open_page_best_effort(driver, "https://example.com")

    assert driver.loaded_urls == ["https://example.com"]
    assert driver.script_calls == ["window.stop();"]
    assert wait_called["count"] == 0


def test_open_page_best_effort_reraises_other_webdriver_errors(monkeypatch):
    runner = LuxNewsRunner(RunConfig(keywords=["k"], medias=["rtl.lu"]))
    driver = _DummyDriver(get_exc=WebDriverException("ERR_CONNECTION_RESET"))

    monkeypatch.setattr(core_module, "wait_for_ready", lambda *_: None)

    with pytest.raises(WebDriverException):
        runner._open_page_best_effort(driver, "https://example.com")
