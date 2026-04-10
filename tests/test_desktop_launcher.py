from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

from luxnews import desktop_launcher


def test_bool_from_env_honors_falsey_values(monkeypatch) -> None:
    monkeypatch.setenv("LUXNEWS_BROWSER_AUTO_OPEN", "0")
    assert desktop_launcher._bool_from_env("LUXNEWS_BROWSER_AUTO_OPEN", default=True) is False


def test_resolve_port_validates_env(monkeypatch) -> None:
    monkeypatch.setenv("LUXNEWS_STREAMLIT_PORT", "8765")
    assert desktop_launcher._resolve_port() == 8765


def test_resolve_app_path_finds_source_script() -> None:
    app_path = desktop_launcher._resolve_app_path()
    assert app_path.name == "streamlit_app.py"
    assert app_path.exists()
    assert app_path == Path(desktop_launcher.__file__).resolve().with_name("streamlit_app.py")


def test_resolve_browser_backend_defaults_to_system_in_source_checkout(monkeypatch) -> None:
    monkeypatch.delenv("LUXNEWS_BROWSER_BACKEND", raising=False)
    monkeypatch.delattr(sys, "frozen", raising=False)

    assert desktop_launcher._resolve_browser_backend(auto_open_browser=True) == "system"


def test_resolve_browser_backend_defaults_to_system_in_packaged_app(monkeypatch) -> None:
    monkeypatch.delenv("LUXNEWS_BROWSER_BACKEND", raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    assert desktop_launcher._resolve_browser_backend(auto_open_browser=True) == "system"


def test_resolve_browser_backend_returns_none_when_auto_open_disabled(monkeypatch) -> None:
    monkeypatch.setenv("LUXNEWS_BROWSER_BACKEND", "playwright")

    assert desktop_launcher._resolve_browser_backend(auto_open_browser=False) == "none"


def test_resolve_browser_backend_accepts_explicit_playwright_override(monkeypatch) -> None:
    monkeypatch.setenv("LUXNEWS_BROWSER_BACKEND", "playwright")

    assert desktop_launcher._resolve_browser_backend(auto_open_browser=True) == "playwright"


def test_build_flag_options_keeps_streamlit_headed_only_for_system_browser() -> None:
    assert desktop_launcher._build_flag_options(port=8501, browser_backend="system")[
        "server_headless"
    ] is False
    assert desktop_launcher._build_flag_options(port=8501, browser_backend="playwright")[
        "server_headless"
    ] is True


def test_run_self_test_imports_selenium_helpers(monkeypatch) -> None:
    calls = []

    def fake_build_options(driver_name: str, headless: bool, open_devtools: bool):
        calls.append((driver_name, headless, open_devtools))
        return object()

    monkeypatch.setitem(
        sys.modules,
        "luxnews.selenium_utils",
        SimpleNamespace(_build_options=fake_build_options),
    )

    desktop_launcher._run_self_test("selenium_imports")

    assert calls == [
        ("chrome", True, False),
        ("edge", True, False),
    ]


def test_run_self_test_imports_browser_helpers(monkeypatch) -> None:
    calls = []
    playwright_calls = []

    def fake_build_options(driver_name: str, headless: bool, open_devtools: bool):
        calls.append((driver_name, headless, open_devtools))
        return object()

    def fake_self_test_playwright_runtime() -> None:
        playwright_calls.append("playwright")

    monkeypatch.setitem(
        sys.modules,
        "luxnews.selenium_utils",
        SimpleNamespace(_build_options=fake_build_options),
    )
    monkeypatch.setitem(
        sys.modules,
        "luxnews.playwright_utils",
        SimpleNamespace(self_test_playwright_runtime=fake_self_test_playwright_runtime),
    )

    desktop_launcher._run_self_test("browser_imports")

    assert calls == [
        ("chrome", True, False),
        ("edge", True, False),
    ]
    assert playwright_calls == ["playwright"]


def test_start_browser_launcher_starts_background_thread(monkeypatch) -> None:
    started = []

    class FakeThread:
        def __init__(self, *, target, kwargs, name, daemon):
            self.target = target
            self.kwargs = kwargs
            self.name = name
            self.daemon = daemon

        def start(self) -> None:
            started.append(self.kwargs)

    monkeypatch.setitem(
        sys.modules,
        "luxnews.playwright_utils",
        SimpleNamespace(ensure_playwright_browser=lambda: Path("/tmp/playwright-browser")),
    )
    monkeypatch.setattr(desktop_launcher.threading, "Thread", FakeThread)

    thread = desktop_launcher._start_browser_launcher(browser_backend="playwright", port=8501)

    assert isinstance(thread, FakeThread)
    assert started == [{"executable_path": Path("/tmp/playwright-browser"), "port": 8501}]


def test_start_browser_launcher_skips_non_playwright_backends() -> None:
    assert desktop_launcher._start_browser_launcher(browser_backend="system", port=8501) is None


def test_should_show_error_dialog_is_disabled_for_self_test(monkeypatch) -> None:
    monkeypatch.setenv("LUXNEWS_DESKTOP_SELFTEST", "browser_imports")

    assert desktop_launcher._should_show_error_dialog() is False
