from __future__ import annotations

import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

try:
    from selenium.webdriver.chrome.options import Options as ChromeOptions
    from selenium.webdriver.edge.options import Options as EdgeOptions
    import luxnews.selenium_utils as selenium_utils
except ModuleNotFoundError:
    ChromeOptions = None
    EdgeOptions = None
    selenium_utils = None


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_build_options_returns_concrete_chrome_options() -> None:
    options = selenium_utils._build_options("chrome", headless=True, open_devtools=True)

    assert isinstance(options, ChromeOptions)
    assert "--headless=new" in options.arguments
    assert "--auto-open-devtools-for-tabs" in options.arguments


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_build_options_returns_concrete_edge_options() -> None:
    options = selenium_utils._build_options("edge", headless=False, open_devtools=False)

    assert isinstance(options, EdgeOptions)
    assert "--headless=new" not in options.arguments
    assert "--auto-open-devtools-for-tabs" not in options.arguments


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_create_driver_delegates_to_playwright(monkeypatch) -> None:
    calls = []
    quit_calls = []

    class DriverStub:
        def quit(self) -> None:
            quit_calls.append("quit")

    expected_driver = DriverStub()

    def fake_create_playwright_driver(
        *,
        headless: bool,
        open_devtools: bool,
        enable_logging: bool,
        page_timeout: float,
        cache_dir=None,
    ):
        calls.append((headless, open_devtools, enable_logging, page_timeout, cache_dir))
        return expected_driver

    monkeypatch.setitem(
        sys.modules,
        "luxnews.playwright_utils",
        SimpleNamespace(create_playwright_driver=fake_create_playwright_driver),
    )

    driver = selenium_utils.create_driver(
        "playwright",
        headless=True,
        open_devtools=False,
        enable_logging=True,
        page_timeout=42.0,
    )

    assert driver is expected_driver
    assert calls == [(True, False, True, 42.0, None)]
    driver.quit()
    assert quit_calls == ["quit"]


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_print_to_pdf_uses_driver_save_pdf_when_available(tmp_path) -> None:
    calls = []

    class DriverStub:
        def execute_async_script(self, script, timeout_ms):
            calls.append(("prepare", timeout_ms))

        def save_pdf(
            self,
            output_path,
            *,
            print_background: bool,
            prefer_css_page_size: bool,
            scale: float,
        ):
            calls.append(
                (
                    "save_pdf",
                    output_path,
                    print_background,
                    prefer_css_page_size,
                    scale,
                )
            )

    output_path = tmp_path / "article.pdf"
    selenium_utils.print_to_pdf(DriverStub(), output_path)

    assert calls[0] == ("prepare", 20_000)
    assert calls[1] == ("save_pdf", output_path, True, True, 0.75)


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_close_active_driver_quits_tracked_driver() -> None:
    calls = []

    class DriverStub:
        def quit(self) -> None:
            calls.append("quit")

    driver = selenium_utils._track_driver(DriverStub())

    assert selenium_utils.close_active_driver() is True
    assert calls == ["quit"]

    driver.quit()
    assert calls == ["quit", "quit"]


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_close_active_driver_returns_false_without_driver() -> None:
    selenium_utils._ACTIVE_DRIVER = None
    assert selenium_utils.close_active_driver() is False


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_login_luxtimes_uses_luxtimes_mediahuis_login_url(monkeypatch) -> None:
    class ElementStub:
        def __init__(self, name: str):
            self.name = name
            self.values: list[str] = []
            self.clicked = False

        def clear(self) -> None:
            self.values.append("clear")

        def send_keys(self, value) -> None:
            self.values.append(str(value))

        def click(self) -> None:
            self.clicked = True

    class DriverStub:
        def __init__(self) -> None:
            self.loaded_urls: list[str] = []
            self.current_url = "https://www.luxtimes.lu/"

        def get(self, url: str) -> None:
            self.loaded_urls.append(url)
            self.current_url = url

    driver = DriverStub()
    username_input = ElementStub("username")
    password_input = ElementStub("password")
    submit_button = ElementStub("submit")
    cookie_checks = {"count": 0}

    def _has_cookie(_driver) -> bool:
        cookie_checks["count"] += 1
        return cookie_checks["count"] > 1

    def _wait_for_first_displayed(_driver, selectors, _timeout):
        selector_values = [value for _by, value in selectors]
        if "username" in selector_values:
            return username_input
        return password_input

    monkeypatch.setattr(selenium_utils, "_has_mediahuis_login_cookie", _has_cookie)
    monkeypatch.setattr(selenium_utils, "wait_for_ready", lambda *_: None)
    monkeypatch.setattr(selenium_utils, "_wait_for_first_displayed", _wait_for_first_displayed)
    monkeypatch.setattr(selenium_utils, "_find_first_displayed", lambda *_: submit_button)

    assert selenium_utils.login_luxtimes(
        driver,
        username="user@example.com",
        password="secret",
        wait_timeout=1,
    )

    login_url = driver.loaded_urls[0]
    parsed = urlparse(login_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "www.luxtimes.lu"
    assert parsed.path == "/auth/login"
    assert parse_qs(parsed.query)["returnTo"] == ["https://www.luxtimes.lu/"]
    assert username_input.values == ["clear", "user@example.com"]
    assert password_input.values == ["clear", "secret"]
    assert submit_button.clicked is True
