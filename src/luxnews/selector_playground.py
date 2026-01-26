from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from bs4 import BeautifulSoup
from lxml import etree
from selenium.webdriver.common.by import By

from luxnews.selenium_utils import create_driver, wait_for_ready


@dataclass
class SelectorMatch:
    text: str
    href: Optional[str]


@dataclass
class SelectorReport:
    count: int
    matches: list[SelectorMatch]


@dataclass
class PlaygroundResult:
    css: Optional[SelectorReport] = None
    xpath: Optional[SelectorReport] = None
    screenshot_path: Optional[str] = None


def run_selector_playground(
    html_path: Optional[Path] = None,
    url: Optional[str] = None,
    css: Optional[str] = None,
    xpath: Optional[str] = None,
    limit: int = 5,
    report_path: Optional[Path] = None,
    screenshot_path: Optional[Path] = None,
    driver_name: str = "chrome",
    headless: bool = True,
) -> PlaygroundResult:
    if not html_path and not url:
        raise ValueError("Provide html_path or url")

    result = PlaygroundResult()

    if html_path:
        html = html_path.read_text(encoding="utf-8")
        if css:
            result.css = _run_css_offline(html, css, limit)
        if xpath:
            result.xpath = _run_xpath_offline(html, xpath, limit)
    else:
        driver = create_driver(driver_name, headless, open_devtools=False, enable_logging=False, page_timeout=30.0)
        try:
            driver.get(url)
            wait_for_ready(driver, 20.0)
            if screenshot_path:
                try:
                    driver.save_screenshot(str(screenshot_path))
                    result.screenshot_path = str(screenshot_path)
                except Exception:  # noqa: BLE001
                    pass
            if css:
                result.css = _run_css_live(driver, css, limit)
            if xpath:
                result.xpath = _run_xpath_live(driver, xpath, limit)
        finally:
            driver.quit()

    if report_path:
        report_path.write_text(json.dumps(_serialize_result(result), indent=2), encoding="utf-8")
    return result


def _run_css_offline(html: str, selector: str, limit: int) -> SelectorReport:
    soup = BeautifulSoup(html, "lxml")
    elements = soup.select(selector)
    matches = []
    for element in elements[:limit]:
        text = element.get_text(strip=True)
        href = element.get("href")
        matches.append(SelectorMatch(text=text, href=href))
    return SelectorReport(count=len(elements), matches=matches)


def _run_xpath_offline(html: str, selector: str, limit: int) -> SelectorReport:
    tree = etree.HTML(html)
    elements = tree.xpath(selector)
    matches = []
    for element in elements[:limit]:
        text = "".join(element.itertext()).strip() if hasattr(element, "itertext") else str(element)
        href = element.get("href") if hasattr(element, "get") else None
        matches.append(SelectorMatch(text=text, href=href))
    return SelectorReport(count=len(elements), matches=matches)


def _run_css_live(driver, selector: str, limit: int) -> SelectorReport:
    elements = driver.find_elements(By.CSS_SELECTOR, selector)
    matches = []
    for element in elements[:limit]:
        matches.append(SelectorMatch(text=element.text.strip(), href=element.get_attribute("href")))
    return SelectorReport(count=len(elements), matches=matches)


def _run_xpath_live(driver, selector: str, limit: int) -> SelectorReport:
    elements = driver.find_elements(By.XPATH, selector)
    matches = []
    for element in elements[:limit]:
        matches.append(SelectorMatch(text=element.text.strip(), href=element.get_attribute("href")))
    return SelectorReport(count=len(elements), matches=matches)


def _serialize_result(result: PlaygroundResult) -> dict:
    def serialize_report(report: SelectorReport):
        return {
            "count": report.count,
            "matches": [
                {"text": match.text, "href": match.href} for match in report.matches
            ],
        }

    payload: dict = {}
    if result.css:
        payload["css"] = serialize_report(result.css)
    if result.xpath:
        payload["xpath"] = serialize_report(result.xpath)
    if result.screenshot_path:
        payload["screenshot_path"] = result.screenshot_path
    return payload
