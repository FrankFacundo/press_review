from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

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


class _EnvAwareSyncPlaywrightStub:
    def __init__(self, runtime: _RuntimeStub, captured_paths: list[str | None]) -> None:
        self._runtime = runtime
        self._captured_paths = captured_paths

    def start(self) -> _RuntimeStub:
        self._captured_paths.append(os.environ.get("PLAYWRIGHT_BROWSERS_PATH"))
        return self._runtime


class _EnvRuntimeStub:
    def __init__(self, executable_path: str) -> None:
        self.chromium = SimpleNamespace(executable_path=executable_path)
        self.stop_calls = 0

    def stop(self):
        self.stop_calls += 1


class _EnvSyncPlaywrightStub:
    def start(self) -> _EnvRuntimeStub:
        browsers_path = Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])
        override = os.environ.get("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE")
        executable_name = "chrome.exe" if override == "win64" else "chrome"
        return _EnvRuntimeStub(str(browsers_path / "chromium-1" / executable_name))


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


def test_create_playwright_driver_sets_browsers_path_only_during_runtime_start(
    monkeypatch, tmp_path: Path
) -> None:
    runtime = _RuntimeStub()
    captured_paths: list[str | None] = []
    cache_dir = tmp_path / "cache"
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.setattr(
        playwright_utils,
        "ensure_playwright_browser",
        lambda browser_name=playwright_utils.PLAYWRIGHT_BROWSER_NAME, cache_dir=None: cache_dir / "chromium",
    )
    monkeypatch.setattr(
        playwright_utils,
        "_load_playwright_sync_api",
        lambda: (lambda: _EnvAwareSyncPlaywrightStub(runtime, captured_paths), Exception, TimeoutError),
    )

    playwright_utils.create_playwright_driver(
        headless=True,
        open_devtools=False,
        enable_logging=False,
        page_timeout=30.0,
        cache_dir=cache_dir,
    )

    assert captured_paths == [str(cache_dir / "browsers")]
    assert "PLAYWRIGHT_BROWSERS_PATH" not in os.environ


def test_resolve_playwright_executable_uses_host_platform_override(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("PLAYWRIGHT_BROWSERS_PATH", raising=False)
    monkeypatch.delenv("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", raising=False)
    monkeypatch.setattr(
        playwright_utils,
        "_load_playwright_sync_api",
        lambda: (lambda: _EnvSyncPlaywrightStub(), Exception, TimeoutError),
    )

    executable_path = playwright_utils.resolve_playwright_executable(
        cache_dir=tmp_path,
        host_platform_override="win64",
    )

    assert executable_path == tmp_path / "browsers" / "chromium-1" / "chrome.exe"
    assert "PLAYWRIGHT_BROWSERS_PATH" not in os.environ
    assert "PLAYWRIGHT_HOST_PLATFORM_OVERRIDE" not in os.environ


def test_resolve_playwright_install_targets_deduplicates_aliases() -> None:
    assert playwright_utils.resolve_playwright_install_targets(
        ["current", "windows", "win64", "windows-x64"]
    ) == ["current", "windows-x64"]
