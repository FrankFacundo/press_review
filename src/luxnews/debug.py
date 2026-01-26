from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver

from luxnews.models import DebugArtifacts
from luxnews.selenium_utils import capture_mhtml, capture_screenshot, get_logs
from luxnews.utils import ensure_dir

LOGGER = logging.getLogger(__name__)


@dataclass
class DebugOptions:
    enabled: bool
    output_dir: Path
    run_id: str


class DebugManager:
    def __init__(self, options: DebugOptions):
        self.options = options
        self._counters: dict[tuple[str, str], int] = {}

    def dump_page(
        self,
        driver: WebDriver,
        media: str,
        kind: str,
        url: str,
        selectors: Optional[list[str]] = None,
        detected_date: Optional[str] = None,
    ) -> DebugArtifacts:
        if not self.options.enabled:
            return DebugArtifacts()

        base_dir = ensure_dir(
            self.options.output_dir / "debug" / self.options.run_id / media / kind
        )
        key = (media, kind)
        count = self._counters.get(key, 0) + 1
        self._counters[key] = count
        page_dir = ensure_dir(base_dir / f"{count:04d}")

        artifacts = DebugArtifacts()
        html_path = page_dir / "page.html"
        html_path.write_text(driver.page_source or "", encoding="utf-8")
        artifacts.html_path = str(html_path)

        mhtml_path = page_dir / "page.mhtml"
        capture_mhtml(driver, mhtml_path)
        if mhtml_path.exists():
            artifacts.mhtml_path = str(mhtml_path)

        screenshot_path = page_dir / "page.png"
        capture_screenshot(driver, screenshot_path)
        if screenshot_path.exists():
            artifacts.screenshot_path = str(screenshot_path)

        console_logs = get_logs(driver, "browser")
        if console_logs:
            console_path = page_dir / "console.json"
            console_path.write_text(json.dumps(console_logs, indent=2), encoding="utf-8")
            artifacts.console_log_path = str(console_path)

        perf_logs = get_logs(driver, "performance")
        if perf_logs:
            perf_path = page_dir / "performance.json"
            perf_path.write_text(json.dumps(perf_logs, indent=2), encoding="utf-8")
            artifacts.performance_log_path = str(perf_path)

        bundle = {
            "url": url,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "title": self._safe_title(driver),
            "detected_publish_date": detected_date,
            "cookies": self._redact_cookies(driver.get_cookies()),
            "selector_counts": self._selector_counts(driver, selectors or []),
        }
        bundle_path = page_dir / "debug_bundle.json"
        bundle_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
        artifacts.bundle_path = str(bundle_path)
        return artifacts

    def _selector_counts(self, driver: WebDriver, selectors: list[str]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for selector in selectors:
            try:
                counts[selector] = len(driver.find_elements(By.CSS_SELECTOR, selector))
            except Exception as exc:  # noqa: BLE001
                LOGGER.debug("Selector count failed for %s: %s", selector, exc)
                counts[selector] = 0
        return counts

    def _redact_cookies(self, cookies: list[dict]) -> list[dict]:
        redacted: list[dict] = []
        for cookie in cookies:
            item = {k: v for k, v in cookie.items() if k != "value"}
            item["value"] = "***"
            redacted.append(item)
        return redacted

    def _safe_title(self, driver: WebDriver) -> Optional[str]:
        try:
            return driver.title
        except Exception:  # noqa: BLE001
            return None
