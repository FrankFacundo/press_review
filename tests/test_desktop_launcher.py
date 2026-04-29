from __future__ import annotations

import sys
from types import SimpleNamespace
from pathlib import Path

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


def test_run_self_test_imports_browser_helpers(monkeypatch) -> None:
    playwright_calls = []

    def fake_self_test_playwright_imports() -> None:
        playwright_calls.append("playwright")

    monkeypatch.setitem(
        sys.modules,
        "luxnews.browser_utils",
        SimpleNamespace(),
    )
    monkeypatch.setitem(
        sys.modules,
        "luxnews.playwright_utils",
        SimpleNamespace(self_test_playwright_imports=fake_self_test_playwright_imports),
    )

    desktop_launcher._run_self_test("browser_imports")

    assert playwright_calls == ["playwright"]
