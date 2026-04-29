from __future__ import annotations

import sys
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import pytest

import luxnews.browser_utils as browser_utils
from luxnews.browser_types import BrowserTimeoutError, BrowserError


def test_create_driver_rejects_non_playwright_driver() -> None:
    with pytest.raises(ValueError, match="playwright"):
        browser_utils.create_driver(
            "chrome",
            headless=True,
            open_devtools=False,
            enable_logging=False,
            page_timeout=30.0,
        )


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

    driver = browser_utils.create_driver(
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
    browser_utils.print_to_pdf(DriverStub(), output_path)

    assert calls[0] == ("prepare", 20_000)
    assert calls[1] == ("save_pdf", output_path, True, True, 0.75)


def test_print_to_pdf_requires_playwright_pdf_support(tmp_path) -> None:
    class DriverStub:
        def execute_async_script(self, *_):
            return None

    with pytest.raises(BrowserError, match="PDF export"):
        browser_utils.print_to_pdf(DriverStub(), tmp_path / "article.pdf")


def test_close_active_driver_quits_tracked_driver() -> None:
    calls = []

    class DriverStub:
        def quit(self) -> None:
            calls.append("quit")

    driver = browser_utils._track_driver(DriverStub())

    assert browser_utils.close_active_driver() is True
    assert calls == ["quit"]

    driver.quit()
    assert calls == ["quit", "quit"]


def test_close_active_driver_returns_false_without_driver() -> None:
    browser_utils._ACTIVE_DRIVER = None
    assert browser_utils.close_active_driver() is False


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

    monkeypatch.setattr(browser_utils, "_has_mediahuis_login_cookie", _has_cookie)
    monkeypatch.setattr(browser_utils, "wait_for_ready", lambda *_: None)
    monkeypatch.setattr(browser_utils, "_wait_for_first_displayed", _wait_for_first_displayed)
    monkeypatch.setattr(browser_utils, "_find_first_displayed", lambda *_: submit_button)

    assert browser_utils.login_luxtimes(
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


def test_contacto_cookie_detection_accepts_rotated_auth0_id_token() -> None:
    class DriverStub:
        def get_cookie(self, _name: str):
            return None

        def get_cookies(self):
            return [{"name": "auth0_rotated-client_id_token", "value": "token"}]

    assert browser_utils._has_contacto_login_cookie(DriverStub()) is True


def test_login_contacto_does_not_reuse_cookie_before_contacto_domain(monkeypatch) -> None:
    class DriverStub:
        def __init__(self) -> None:
            self.current_url = "https://www.wort.lu/"
            self.loaded_urls: list[str] = []

        def get(self, url: str) -> None:
            self.loaded_urls.append(url)
            self.current_url = url

    driver = DriverStub()

    monkeypatch.setattr(browser_utils, "_has_contacto_login_cookie", lambda *_: True)
    monkeypatch.setattr(browser_utils, "wait_for_ready", lambda *_: None)
    monkeypatch.setattr(
        browser_utils,
        "_wait_for_first_displayed",
        lambda *_: (_ for _ in ()).throw(BrowserTimeoutError()),
    )

    assert browser_utils.login_contacto(
        driver,
        email="user@example.com",
        password="secret",
        wait_timeout=1,
    )
    assert driver.loaded_urls == [
        "https://www.contacto.lu/auth/login?returnTo=https%3A%2F%2Fwww.contacto.lu%2F"
    ]
