from __future__ import annotations

from pathlib import Path

from luxnews import playwright_utils


class _KeyboardStub:
    def press(self, *_args, **_kwargs):
        return None

    def type(self, *_args, **_kwargs):
        return None


class _PageStub:
    def __init__(self) -> None:
        self.keyboard = _KeyboardStub()

    def on(self, *_args, **_kwargs):
        return None

    def set_default_navigation_timeout(self, *_args, **_kwargs):
        return None

    def set_default_timeout(self, *_args, **_kwargs):
        return None


class _ContextStub:
    def new_page(self) -> _PageStub:
        return _PageStub()

    def close(self):
        return None


class _BrowserStub:
    def __init__(self) -> None:
        self.new_context_calls = []

    def new_context(self, **kwargs):
        self.new_context_calls.append(kwargs)
        return _ContextStub()

    def close(self):
        return None


class _ChromiumStub:
    def __init__(self) -> None:
        self.launch_calls = []
        self.browser = _BrowserStub()

    def launch(self, **kwargs):
        self.launch_calls.append(kwargs)
        return self.browser


class _RuntimeStub:
    def __init__(self) -> None:
        self.chromium = _ChromiumStub()
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class _SyncPlaywrightStub:
    def __init__(self, runtime: _RuntimeStub) -> None:
        self._runtime = runtime

    def start(self) -> _RuntimeStub:
        return self._runtime


def test_create_playwright_driver_uses_browser_flag_for_devtools(monkeypatch, tmp_path: Path) -> None:
    runtime = _RuntimeStub()

    monkeypatch.setattr(
        playwright_utils,
        "ensure_playwright_browser",
        lambda browser_name=playwright_utils.PLAYWRIGHT_BROWSER_NAME, cache_dir=None: tmp_path / "chromium",
    )
    monkeypatch.setattr(
        playwright_utils,
        "_load_playwright_sync_api",
        lambda: (lambda: _SyncPlaywrightStub(runtime), Exception, TimeoutError),
    )

    driver = playwright_utils.create_playwright_driver(
        headless=False,
        open_devtools=True,
        enable_logging=False,
        page_timeout=30.0,
    )

    launch_kwargs = runtime.chromium.launch_calls[0]
    assert "devtools" not in launch_kwargs
    assert "--auto-open-devtools-for-tabs" in launch_kwargs["args"]
    assert isinstance(driver, playwright_utils.PlaywrightDriver)
