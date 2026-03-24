from __future__ import annotations

import sys
from types import SimpleNamespace

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
    expected_driver = object()
    calls = []

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
