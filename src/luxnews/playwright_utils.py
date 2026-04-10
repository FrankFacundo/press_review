from __future__ import annotations

import logging
import os
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from luxnews.config import (
    PLAYWRIGHT_WINDOWS_X64,
    get_playwright_cache_dir,
    get_playwright_default_cache_dir,
    is_packaged_app,
)

LOGGER = logging.getLogger(__name__)
PLAYWRIGHT_BROWSER_NAME = "chromium"
PLAYWRIGHT_INSTALL_TARGET_CURRENT = "current"
PLAYWRIGHT_INSTALL_TARGET_WINDOWS_X64 = PLAYWRIGHT_WINDOWS_X64
PLAYWRIGHT_INSTALL_TARGET_ALIASES = {
    PLAYWRIGHT_INSTALL_TARGET_CURRENT: PLAYWRIGHT_INSTALL_TARGET_CURRENT,
    "windows": PLAYWRIGHT_INSTALL_TARGET_WINDOWS_X64,
    "windows-intel": PLAYWRIGHT_INSTALL_TARGET_WINDOWS_X64,
    "windows-x64": PLAYWRIGHT_INSTALL_TARGET_WINDOWS_X64,
    "win-x64": PLAYWRIGHT_INSTALL_TARGET_WINDOWS_X64,
    "win64": PLAYWRIGHT_INSTALL_TARGET_WINDOWS_X64,
}
PLAYWRIGHT_HOST_PLATFORM_OVERRIDES = {
    PLAYWRIGHT_INSTALL_TARGET_WINDOWS_X64: "win64",
}
_CONTROL_KEYS = {Keys.CONTROL}
_META_KEYS = {Keys.META, Keys.COMMAND}


def _load_playwright_sync_api():
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "Playwright is not installed. Run `python3 -m pip install -e .` first."
        ) from exc
    return sync_playwright, PlaywrightError, PlaywrightTimeoutError


def self_test_playwright_imports() -> None:
    _load_playwright_sync_api()


def self_test_playwright_runtime(cache_dir: Path | None = None) -> Path:
    executable_path = resolve_playwright_executable(cache_dir=cache_dir)
    if not executable_path.exists():
        raise RuntimeError(
            "Playwright browser executable is missing from the configured cache: "
            f"{executable_path}"
        )
    return executable_path


def get_playwright_browser_cache_dir() -> Path:
    return get_playwright_cache_dir()


def configure_playwright_environment(
    cache_dir: Path | None = None,
    *,
    host_platform_override: str | None = None,
) -> Path:
    root = Path(cache_dir or get_playwright_browser_cache_dir()).expanduser()
    browsers_dir = root / "browsers"
    browsers_dir.mkdir(parents=True, exist_ok=True)
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    if host_platform_override:
        os.environ["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = host_platform_override
    else:
        os.environ.pop("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", None)
    return browsers_dir


@contextmanager
def _temporary_playwright_environment(
    cache_dir: Path | None = None,
    *,
    host_platform_override: str | None = None,
):
    previous_browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    previous_host_platform = os.environ.get("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE")
    browsers_dir = configure_playwright_environment(
        cache_dir,
        host_platform_override=host_platform_override,
    )
    try:
        yield browsers_dir
    finally:
        if previous_browsers_path is None:
            os.environ.pop("PLAYWRIGHT_BROWSERS_PATH", None)
        else:
            os.environ["PLAYWRIGHT_BROWSERS_PATH"] = previous_browsers_path

        if previous_host_platform is None:
            os.environ.pop("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", None)
        else:
            os.environ["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = previous_host_platform


def resolve_playwright_executable(
    browser_name: str = PLAYWRIGHT_BROWSER_NAME,
    cache_dir: Path | None = None,
    *,
    host_platform_override: str | None = None,
) -> Path:
    sync_playwright, _, _ = _load_playwright_sync_api()
    with _temporary_playwright_environment(
        cache_dir,
        host_platform_override=host_platform_override,
    ):
        runtime = sync_playwright().start()
        try:
            browser_type = getattr(runtime, browser_name)
            executable_path = Path(browser_type.executable_path)
        finally:
            runtime.stop()
    return executable_path


def is_playwright_browser_installed(
    browser_name: str = PLAYWRIGHT_BROWSER_NAME,
    cache_dir: Path | None = None,
    *,
    host_platform_override: str | None = None,
) -> bool:
    return resolve_playwright_executable(
        browser_name=browser_name,
        cache_dir=cache_dir,
        host_platform_override=host_platform_override,
    ).exists()


def install_playwright_browser(
    browser_name: str = PLAYWRIGHT_BROWSER_NAME,
    cache_dir: Path | None = None,
    *,
    host_platform_override: str | None = None,
) -> Path:
    if is_packaged_app():
        raise RuntimeError(
            "Packaged LuxNews cannot download Playwright browser assets at runtime. "
            "Rebuild the desktop package after running `luxnews install-playwright` first."
        )

    root = Path(cache_dir or get_playwright_browser_cache_dir()).expanduser()
    browsers_dir = root / "browsers"
    browsers_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers_dir)
    if host_platform_override:
        env["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = host_platform_override
    else:
        env.pop("PLAYWRIGHT_HOST_PLATFORM_OVERRIDE", None)
    command = [sys.executable, "-m", "playwright", "install", browser_name]
    LOGGER.info("Installing Playwright browser assets into %s", browsers_dir)
    try:
        completed = subprocess.run(
            command,
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Unable to run the Playwright installer. Check that the current Python "
            "environment is valid."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = (exc.stderr or "").strip()
        stdout = (exc.stdout or "").strip()
        details = stderr or stdout or str(exc)
        raise RuntimeError(f"Playwright browser install failed: {details}") from exc

    if completed.stdout:
        LOGGER.info("%s", completed.stdout.strip())
    executable_path = resolve_playwright_executable(
        browser_name=browser_name,
        cache_dir=cache_dir,
        host_platform_override=host_platform_override,
    )
    if not executable_path.exists():
        raise RuntimeError(
            f"Playwright installer finished but browser executable is still missing: {executable_path}"
        )
    return executable_path


def ensure_playwright_browser(
    browser_name: str = PLAYWRIGHT_BROWSER_NAME,
    cache_dir: Path | None = None,
    *,
    host_platform_override: str | None = None,
) -> Path:
    executable_path = resolve_playwright_executable(
        browser_name=browser_name,
        cache_dir=cache_dir,
        host_platform_override=host_platform_override,
    )
    if executable_path.exists():
        return executable_path
    return install_playwright_browser(
        browser_name=browser_name,
        cache_dir=cache_dir,
        host_platform_override=host_platform_override,
    )


def normalize_playwright_install_target(target: str) -> str:
    normalized = (target or "").strip().lower()
    if not normalized:
        raise ValueError("Playwright install target cannot be empty.")
    try:
        return PLAYWRIGHT_INSTALL_TARGET_ALIASES[normalized]
    except KeyError as exc:
        valid_targets = ", ".join(sorted({"current", "windows-x64"}))
        raise ValueError(
            f"Unsupported Playwright install target: {target!r}. Use one of: {valid_targets}."
        ) from exc


def resolve_playwright_install_targets(targets: list[str] | tuple[str, ...]) -> list[str]:
    if not targets:
        return [PLAYWRIGHT_INSTALL_TARGET_CURRENT]

    resolved: list[str] = []
    for target in targets:
        normalized = normalize_playwright_install_target(target)
        if normalized not in resolved:
            resolved.append(normalized)
    return resolved


def get_playwright_cache_dir_for_install_target(target: str) -> Path:
    normalized = normalize_playwright_install_target(target)
    if normalized == PLAYWRIGHT_INSTALL_TARGET_CURRENT:
        return get_playwright_default_cache_dir()
    return get_playwright_default_cache_dir(platform_name=normalized)


def get_playwright_host_platform_override_for_install_target(target: str) -> str | None:
    normalized = normalize_playwright_install_target(target)
    return PLAYWRIGHT_HOST_PLATFORM_OVERRIDES.get(normalized)


class PlaywrightDriver:
    def __init__(
        self,
        *,
        runtime,
        browser,
        context,
        page,
        playwright_error,
        playwright_timeout_error,
        enable_logging: bool,
    ) -> None:
        self._runtime = runtime
        self._browser = browser
        self._context = context
        self._page = page
        self._playwright_error = playwright_error
        self._playwright_timeout_error = playwright_timeout_error
        self._navigation_timeout_ms = 30_000
        self._enable_logging = enable_logging
        self._browser_logs: list[dict[str, Any]] = []
        self._performance_logs: list[dict[str, Any]] = []
        if enable_logging:
            self._attach_log_listeners()

    @property
    def current_url(self) -> str:
        return self._page.url

    @property
    def page_source(self) -> str:
        return self._call(self._page.content)

    @property
    def title(self) -> str:
        return self._call(self._page.title)

    def _attach_log_listeners(self) -> None:
        self._page.on("console", self._record_console_message)
        self._page.on("pageerror", self._record_page_error)
        self._page.on("requestfailed", self._record_request_failed)
        self._page.on("response", self._record_response)

    def _record_console_message(self, message) -> None:
        entry = {
            "level": _maybe_call(getattr(message, "type", "info")),
            "message": _maybe_call(getattr(message, "text", "")),
            "source": "console",
        }
        self._browser_logs.append(entry)

    def _record_page_error(self, error: Exception) -> None:
        self._browser_logs.append(
            {
                "level": "error",
                "message": str(error),
                "source": "pageerror",
            }
        )

    def _record_request_failed(self, request) -> None:
        failure = _maybe_call(getattr(request, "failure", None))
        if isinstance(failure, dict):
            failure_text = failure.get("errorText")
        elif failure:
            failure_text = str(failure)
        else:
            failure_text = None
        self._performance_logs.append(
            {
                "type": "requestfailed",
                "url": _maybe_call(getattr(request, "url", "")),
                "method": _maybe_call(getattr(request, "method", "")),
                "failure": failure_text,
            }
        )

    def _record_response(self, response) -> None:
        self._performance_logs.append(
            {
                "type": "response",
                "url": _maybe_call(getattr(response, "url", "")),
                "status": _maybe_call(getattr(response, "status", None)),
                "ok": _maybe_call(getattr(response, "ok", None)),
            }
        )

    def _call(self, func, *args, **kwargs):
        try:
            return func(*args, **kwargs)
        except self._playwright_timeout_error as exc:
            raise TimeoutException(str(exc)) from exc
        except self._playwright_error as exc:
            raise WebDriverException(str(exc)) from exc

    def set_page_load_timeout(self, timeout_seconds: float) -> None:
        timeout_ms = max(int(timeout_seconds * 1000), 1_000)
        self._navigation_timeout_ms = timeout_ms
        self._call(self._page.set_default_navigation_timeout, timeout_ms)
        self._call(self._page.set_default_timeout, timeout_ms)

    def get(self, url: str) -> None:
        self._call(
            self._page.goto,
            url,
            wait_until="load",
            timeout=self._navigation_timeout_ms,
        )

    def quit(self) -> None:
        errors: list[str] = []
        for closer in (self._page.close, self._context.close, self._browser.close, self._runtime.stop):
            try:
                closer()
            except Exception as exc:  # noqa: BLE001
                errors.append(str(exc))
        if errors:
            LOGGER.debug("Playwright shutdown completed with warnings: %s", "; ".join(errors))

    def execute_script(self, script: str, *args):
        script_body = script or ""
        if script_body.strip() == "arguments[0].click();" and len(args) == 1:
            element = args[0]
            if isinstance(element, PlaywrightWebElement):
                element.click()
                return None

        js_args = [self._serialize_script_arg(arg) for arg in args]
        wrapped = """
(payload) => {
  const args = payload.args || [];
  return (function() {
SCRIPT_BODY
  }).apply(null, args);
}
""".replace("SCRIPT_BODY", script_body)
        return self._call(self._page.evaluate, wrapped, {"args": js_args})

    def execute_async_script(self, script: str, *args):
        js_args = [self._serialize_script_arg(arg) for arg in args]
        wrapped = """
(payload) => new Promise((resolve, reject) => {
  const args = Array.from(payload.args || []);
  args.push(resolve);
  try {
    (function() {
SCRIPT_BODY
    }).apply(null, args);
  } catch (error) {
    reject(error);
  }
})
""".replace("SCRIPT_BODY", script or "")
        return self._call(self._page.evaluate, wrapped, {"args": js_args})

    def find_element(self, by: str, value: str):
        elements = self.find_elements(by, value)
        if not elements:
            raise WebDriverException(f"No element found for {by}={value!r}")
        return elements[0]

    def find_elements(self, by: str, value: str):
        strategy, selector = _selector_for(by, value)
        if strategy == "css":
            handles = self._call(self._page.query_selector_all, selector)
        else:
            handles = self._call(self._page.locator(f"xpath={selector}").element_handles)
        return [PlaywrightWebElement(self, handle) for handle in handles if handle is not None]

    def get_cookie(self, name: str) -> dict[str, Any] | None:
        for cookie in self.get_cookies():
            if cookie.get("name") == name:
                return cookie
        return None

    def get_cookies(self) -> list[dict[str, Any]]:
        return self._call(self._context.cookies)

    def save_screenshot(self, output_path: str) -> None:
        self._call(self._page.screenshot, path=output_path, full_page=True)

    def save_pdf(
        self,
        output_path: Path,
        *,
        print_background: bool,
        prefer_css_page_size: bool,
        scale: float,
    ) -> None:
        self._call(
            self._page.pdf,
            path=str(output_path),
            print_background=print_background,
            prefer_css_page_size=prefer_css_page_size,
            scale=scale,
        )

    def capture_mhtml(self, output_path: Path) -> None:
        session = self._call(self._context.new_cdp_session, self._page)
        try:
            result = self._call(session.send, "Page.captureSnapshot", {"format": "mhtml"})
        finally:
            detach = getattr(session, "detach", None)
            if callable(detach):
                try:
                    detach()
                except Exception:  # noqa: BLE001
                    pass
        data = result.get("data") if isinstance(result, dict) else None
        if data:
            output_path.write_text(data, encoding="utf-8")

    def get_log(self, log_type: str) -> list[dict[str, Any]]:
        if log_type == "browser":
            return list(self._browser_logs)
        if log_type == "performance":
            return list(self._performance_logs)
        return []

    def _serialize_script_arg(self, value):
        if isinstance(value, PlaywrightWebElement):
            raise WebDriverException(
                "Passing Playwright elements into execute_script is only supported for click()."
            )
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, list):
            return [self._serialize_script_arg(item) for item in value]
        if isinstance(value, tuple):
            return [self._serialize_script_arg(item) for item in value]
        if isinstance(value, dict):
            return {key: self._serialize_script_arg(item) for key, item in value.items()}
        return value


class PlaywrightWebElement:
    def __init__(self, driver: PlaywrightDriver, handle) -> None:
        self._driver = driver
        self._handle = handle

    @property
    def text(self) -> str:
        return self._driver._call(self._handle.inner_text).strip()

    def click(self) -> None:
        self._driver._call(self._handle.click)

    def clear(self) -> None:
        self._driver._call(self._handle.fill, "")

    def send_keys(self, *values) -> None:
        if not values:
            return
        self._driver._call(self._handle.focus)
        index = 0
        while index < len(values):
            value = values[index]

            if value in _CONTROL_KEYS and index + 1 < len(values):
                modifier = "Meta" if sys.platform == "darwin" else "Control"
                key = _keyboard_key(values[index + 1])
                self._driver._call(self._driver._page.keyboard.press, f"{modifier}+{key}")
                index += 2
                continue

            if value in _META_KEYS and index + 1 < len(values):
                key = _keyboard_key(values[index + 1])
                self._driver._call(self._driver._page.keyboard.press, f"Meta+{key}")
                index += 2
                continue

            key_name = _special_key_name(value)
            if key_name:
                self._driver._call(self._driver._page.keyboard.press, key_name)
            else:
                self._driver._call(self._driver._page.keyboard.type, str(value))
            index += 1

    def is_displayed(self) -> bool:
        script = """
(element) => {
  if (!element) {
    return false;
  }
  const style = window.getComputedStyle(element);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
    return false;
  }
  const rect = element.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
"""
        return bool(self._driver._call(self._handle.evaluate, script))

    def get_attribute(self, name: str) -> str | None:
        return self._driver._call(self._handle.get_attribute, name)


def create_playwright_driver(
    *,
    headless: bool,
    open_devtools: bool,
    enable_logging: bool,
    page_timeout: float,
    cache_dir: Path | None = None,
) -> PlaywrightDriver:
    executable_path = ensure_playwright_browser(cache_dir=cache_dir)
    sync_playwright, playwright_error, playwright_timeout_error = _load_playwright_sync_api()
    with _temporary_playwright_environment(cache_dir):
        runtime = sync_playwright().start()
    launch_args = [
        "--disable-gpu",
        "--disable-dev-shm-usage",
        "--window-size=1400,1000",
    ]
    if open_devtools and not headless:
        launch_args.append("--auto-open-devtools-for-tabs")

    try:
        browser = runtime.chromium.launch(
            headless=headless,
            executable_path=str(executable_path),
            chromium_sandbox=False,
            args=launch_args,
        )
        context = browser.new_context(viewport={"width": 1400, "height": 1000})
        page = context.new_page()
        driver = PlaywrightDriver(
            runtime=runtime,
            browser=browser,
            context=context,
            page=page,
            playwright_error=playwright_error,
            playwright_timeout_error=playwright_timeout_error,
            enable_logging=enable_logging,
        )
        driver.set_page_load_timeout(page_timeout)
        return driver
    except Exception:
        runtime.stop()
        raise


def _selector_for(by: str, value: str) -> tuple[str, str]:
    if by == By.CSS_SELECTOR:
        return "css", value
    if by == By.ID:
        return "css", f'[id="{_escape_css_value(value)}"]'
    if by == By.NAME:
        return "css", f'[name="{_escape_css_value(value)}"]'
    if by == By.XPATH:
        return "xpath", value
    raise WebDriverException(f"Unsupported selector strategy for Playwright: {by}")


def _escape_css_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def _special_key_name(value) -> str | None:
    if value == Keys.ENTER:
        return "Enter"
    if value == Keys.BACKSPACE:
        return "Backspace"
    return None


def _keyboard_key(value) -> str:
    special_key = _special_key_name(value)
    if special_key:
        return special_key
    raw = str(value)
    if len(raw) == 1:
        return raw.upper()
    return raw


def _maybe_call(value):
    return value() if callable(value) else value
