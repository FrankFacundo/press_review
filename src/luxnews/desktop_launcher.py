from __future__ import annotations

import os
import socket
import sys
from pathlib import Path

from streamlit.web import bootstrap

APP_NAME = "LuxNews"
_FALSEY_VALUES = {"0", "false", "no", "off"}


def _bool_from_env(name: str, *, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in _FALSEY_VALUES


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _resolve_port() -> int:
    raw_port = os.getenv("LUXNEWS_STREAMLIT_PORT")
    if not raw_port:
        return _find_free_port()
    try:
        port = int(raw_port)
    except ValueError as exc:
        raise ValueError("LUXNEWS_STREAMLIT_PORT must be an integer.") from exc
    if not 1 <= port <= 65535:
        raise ValueError("LUXNEWS_STREAMLIT_PORT must be between 1 and 65535.")
    return port


def _resolve_app_path() -> Path:
    if getattr(sys, "frozen", False):
        bundle_root = Path(getattr(sys, "_MEIPASS", Path(sys.executable).resolve().parent))
        bundled_app = bundle_root / "luxnews" / "streamlit_app.py"
        if bundled_app.exists():
            return bundled_app

    source_app = Path(__file__).resolve().with_name("streamlit_app.py")
    if source_app.exists():
        return source_app

    raise FileNotFoundError("Could not locate luxnews/streamlit_app.py for the desktop launcher.")


def _show_error_dialog(message: str) -> None:
    try:
        import tkinter as tk
        from tkinter import messagebox
    except Exception:
        print(message, file=sys.stderr)
        return

    root = tk.Tk()
    root.withdraw()
    try:
        messagebox.showerror(APP_NAME, message)
    finally:
        root.destroy()


def _run_self_test(name: str) -> None:
    if name in {"selenium_imports", "browser_imports"}:
        from luxnews.selenium_utils import _build_options

        _build_options("chrome", headless=True, open_devtools=False)
        _build_options("edge", headless=True, open_devtools=False)
        if name == "browser_imports":
            from luxnews.playwright_utils import self_test_playwright_imports

            self_test_playwright_imports()
        return
    raise ValueError(f"Unknown self-test: {name}")


def main() -> None:
    try:
        self_test = os.getenv("LUXNEWS_DESKTOP_SELFTEST")
        if self_test:
            _run_self_test(self_test)
            return

        app_path = _resolve_app_path()
        auto_open_browser = _bool_from_env("LUXNEWS_BROWSER_AUTO_OPEN", default=True)
        port = _resolve_port()
        flag_options = {
            "server_address": "127.0.0.1",
            "server_port": port,
            "server_headless": not auto_open_browser,
            "server_fileWatcherType": "none",
            "browser_serverAddress": "127.0.0.1",
            "browser_gatherUsageStats": False,
            "global_developmentMode": False,
        }
        bootstrap.load_config_options(flag_options)
        bootstrap.run(
            str(app_path),
            False,
            [],
            flag_options,
        )
    except Exception as exc:
        _show_error_dialog(f"{APP_NAME} failed to start.\n\n{exc}")
        raise


__all__ = ["main"]
