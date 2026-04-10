from __future__ import annotations

import os
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from streamlit.web import bootstrap

APP_NAME = "LuxNews"
_FALSEY_VALUES = {"0", "false", "no", "off"}
_BROWSER_BACKEND_ALIASES = {
    "auto": "auto",
    "browser": "system",
    "default": "auto",
    "none": "none",
    "off": "none",
    "playwright": "playwright",
    "system": "system",
}


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


def _resolve_browser_backend(*, auto_open_browser: bool) -> str:
    if not auto_open_browser:
        return "none"

    raw_backend = os.getenv("LUXNEWS_BROWSER_BACKEND", "auto").strip().lower()
    try:
        backend = _BROWSER_BACKEND_ALIASES[raw_backend]
    except KeyError as exc:
        valid_values = ", ".join(sorted(_BROWSER_BACKEND_ALIASES))
        raise ValueError(
            f"LUXNEWS_BROWSER_BACKEND must be one of: {valid_values}."
        ) from exc

    if backend == "auto":
        return "system"
    return backend


def _build_flag_options(*, port: int, browser_backend: str) -> dict[str, object]:
    return {
        "server_address": "127.0.0.1",
        "server_port": port,
        "server_headless": browser_backend != "system",
        "server_fileWatcherType": "none",
        "browser_serverAddress": "127.0.0.1",
        "browser_gatherUsageStats": False,
        "global_developmentMode": False,
    }


def _wait_for_streamlit(port: int, *, timeout_seconds: float = 45.0) -> None:
    deadline = time.monotonic() + timeout_seconds
    health_url = f"http://127.0.0.1:{port}/_stcore/health"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=2.0) as response:
                body = response.read().decode("utf-8", errors="replace").strip().lower()
                if response.status == 200 and "ok" in body:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(0.5)
    raise TimeoutError(f"Timed out waiting for Streamlit healthcheck at {health_url}.")


def _launch_detached_process(command: list[str], *, cwd: Path | None = None) -> None:
    kwargs = {
        "cwd": str(cwd) if cwd is not None else None,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
    }
    if sys.platform.startswith("win"):
        kwargs["creationflags"] = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(
            subprocess,
            "CREATE_NEW_PROCESS_GROUP",
            0,
        )
    else:
        kwargs["start_new_session"] = True
    subprocess.Popen(command, **kwargs)


def _report_browser_launch_error(*, port: int, exc: Exception) -> None:
    url = f"http://127.0.0.1:{port}"
    message = (
        f"{APP_NAME} started but failed to launch the Playwright browser.\n\n{exc}\n\n"
        f"Open {url} manually."
    )
    if _should_show_error_dialog():
        _show_error_dialog(message)
    else:
        print(message, file=sys.stderr)


def _open_playwright_browser_when_ready(*, executable_path: Path, port: int) -> None:
    try:
        _wait_for_streamlit(port)
        _launch_detached_process(
            [str(executable_path), f"http://127.0.0.1:{port}"],
            cwd=executable_path.parent,
        )
    except Exception as exc:
        _report_browser_launch_error(port=port, exc=exc)


def _start_browser_launcher(*, browser_backend: str, port: int) -> threading.Thread | None:
    if browser_backend != "playwright":
        return None

    from luxnews.playwright_utils import ensure_playwright_browser

    executable_path = ensure_playwright_browser()
    thread = threading.Thread(
        target=_open_playwright_browser_when_ready,
        kwargs={
            "executable_path": executable_path,
            "port": port,
        },
        name="luxnews-playwright-browser",
        daemon=True,
    )
    thread.start()
    return thread


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


def _should_show_error_dialog() -> bool:
    if os.getenv("LUXNEWS_DESKTOP_SELFTEST"):
        return False
    return _bool_from_env("LUXNEWS_DISABLE_ERROR_DIALOGS", default=False) is False


def _run_self_test(name: str) -> None:
    if name in {"selenium_imports", "browser_imports"}:
        from luxnews.selenium_utils import _build_options

        _build_options("chrome", headless=True, open_devtools=False)
        _build_options("edge", headless=True, open_devtools=False)
        if name == "browser_imports":
            from luxnews.playwright_utils import self_test_playwright_runtime

            self_test_playwright_runtime()
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
        browser_backend = _resolve_browser_backend(auto_open_browser=auto_open_browser)
        port = _resolve_port()
        flag_options = _build_flag_options(port=port, browser_backend=browser_backend)
        _start_browser_launcher(browser_backend=browser_backend, port=port)
        bootstrap.load_config_options(flag_options)
        bootstrap.run(
            str(app_path),
            False,
            [],
            flag_options,
        )
    except Exception as exc:
        message = f"{APP_NAME} failed to start.\n\n{exc}"
        if _should_show_error_dialog():
            _show_error_dialog(message)
        else:
            print(message, file=sys.stderr)
        raise


__all__ = ["main"]
