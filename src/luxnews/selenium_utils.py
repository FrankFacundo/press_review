from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Optional

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

LOGGER = logging.getLogger(__name__)


def create_driver(
    driver_name: str,
    headless: bool,
    open_devtools: bool,
    enable_logging: bool,
    page_timeout: float,
) -> webdriver.Remote:
    driver_name = driver_name.lower()
    if driver_name not in {"chrome", "edge"}:
        raise ValueError("driver must be 'chrome' or 'edge'")

    options = _build_options(driver_name, headless, open_devtools)
    if enable_logging:
        options.set_capability(
            "goog:loggingPrefs",
            {"browser": "ALL", "performance": "ALL"},
        )

    if driver_name == "chrome":
        driver = webdriver.Chrome(options=options)
    else:
        driver = webdriver.Edge(options=options)

    driver.set_page_load_timeout(page_timeout)
    return driver


def _build_options(driver_name: str, headless: bool, open_devtools: bool):
    if driver_name == "chrome":
        options = webdriver.ChromeOptions()
    else:
        options = webdriver.EdgeOptions()

    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,1000")
    if open_devtools:
        options.add_argument("--auto-open-devtools-for-tabs")
    return options


def wait_for_ready(driver: webdriver.Remote, wait_timeout: float) -> None:
    WebDriverWait(driver, wait_timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def extract_visible_text(driver: webdriver.Remote) -> str:
    try:
        return driver.execute_script("return document.body ? document.body.innerText : ''")
    except WebDriverException:
        return ""


def extract_title(driver: webdriver.Remote) -> Optional[str]:
    try:
        title = driver.title
    except WebDriverException:
        title = None
    if title:
        return title.strip()
    return None


def print_to_pdf(driver: webdriver.Remote, output_path: Path) -> None:
    data = driver.execute_cdp_cmd(
        "Page.printToPDF",
        {
            "printBackground": True,
            "preferCSSPageSize": True,
        },
    )
    pdf_bytes = base64.b64decode(data.get("data", ""))
    output_path.write_bytes(pdf_bytes)


def try_accept_cookies(driver: webdriver.Remote) -> None:
    labels = [
        "accept",
        "agree",
        "ok",
        "j'accepte",
        "accepter",
        "tout accepter",
        "alle akzeptieren",
        "aceitar",
        "allow all",
    ]
    try:
        buttons = driver.find_elements(By.TAG_NAME, "button") + driver.find_elements(
            By.TAG_NAME, "a"
        )
        for button in buttons:
            text = (button.text or "").strip().lower()
            if any(label in text for label in labels):
                button.click()
                time.sleep(0.5)
                break
    except WebDriverException:
        return


def capture_screenshot(driver: webdriver.Remote, output_path: Path) -> None:
    try:
        driver.save_screenshot(str(output_path))
    except WebDriverException as exc:
        LOGGER.debug("Screenshot failed: %s", exc)


def capture_mhtml(driver: webdriver.Remote, output_path: Path) -> None:
    try:
        result = driver.execute_cdp_cmd("Page.captureSnapshot", {"format": "mhtml"})
        data = result.get("data")
        if data:
            output_path.write_text(data, encoding="utf-8")
    except WebDriverException as exc:
        LOGGER.debug("MHTML capture failed: %s", exc)


def get_logs(driver: webdriver.Remote, log_type: str) -> list[dict]:
    try:
        return driver.get_log(log_type)
    except WebDriverException:
        return []
