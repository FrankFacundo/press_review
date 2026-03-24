from __future__ import annotations

import base64
import logging
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.webdriver import WebDriver as ChromeWebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.webdriver import WebDriver as EdgeWebDriver
from selenium.webdriver.remote.webdriver import WebDriver as RemoteWebDriver
from selenium.webdriver.support.ui import WebDriverWait

LOGGER = logging.getLogger(__name__)
WORT_AUTH0_CLIENT_ID = "92cIfq2nCGyCc7meGRMjCJ7T8IBlIxIq"
WORT_ID_TOKEN_COOKIE = f"auth0_{WORT_AUTH0_CLIENT_ID}_id_token"
CONTACTO_AUTH0_CLIENT_ID = "H8NL70vxzZhzeWkgNOfPchPA8wsPayIZ"
CONTACTO_ID_TOKEN_COOKIE = f"auth0_{CONTACTO_AUTH0_CLIENT_ID}_id_token"


def create_driver(
    driver_name: str,
    headless: bool,
    open_devtools: bool,
    enable_logging: bool,
    page_timeout: float,
) -> RemoteWebDriver:
    driver_name = driver_name.lower()
    if driver_name == "playwright":
        from luxnews.playwright_utils import create_playwright_driver

        return create_playwright_driver(
            headless=headless,
            open_devtools=open_devtools,
            enable_logging=enable_logging,
            page_timeout=page_timeout,
        )
    if driver_name not in {"chrome", "edge"}:
        raise ValueError("driver must be 'chrome', 'edge', or 'playwright'")

    options = _build_options(driver_name, headless, open_devtools)
    if enable_logging:
        options.set_capability(
            "goog:loggingPrefs",
            {"browser": "ALL", "performance": "ALL"},
        )

    if driver_name == "chrome":
        driver = ChromeWebDriver(options=options)
    else:
        driver = EdgeWebDriver(options=options)

    driver.set_page_load_timeout(page_timeout)
    return driver


def _build_options(driver_name: str, headless: bool, open_devtools: bool):
    if driver_name == "chrome":
        options = ChromeOptions()
    else:
        options = EdgeOptions()

    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1400,1000")
    if open_devtools:
        options.add_argument("--auto-open-devtools-for-tabs")
    return options


def wait_for_ready(driver: RemoteWebDriver, wait_timeout: float) -> None:
    WebDriverWait(driver, wait_timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )


def extract_visible_text(driver: RemoteWebDriver) -> str:
    try:
        return driver.execute_script("return document.body ? document.body.innerText : ''")
    except WebDriverException:
        return ""


def extract_visible_text_from_selectors(
    driver: RemoteWebDriver,
    selectors: list[str],
    fallback_to_body: bool = True,
) -> str:
    if not selectors:
        return extract_visible_text(driver)

    script = """
const selectors = arguments[0] || [];
const fallbackToBody = Boolean(arguments[1]);
for (const selector of selectors) {
  const node = document.querySelector(selector);
  if (!node) {
    continue;
  }
  const text = (node.innerText || '').trim();
  if (text) {
    return text;
  }
}
if (fallbackToBody && document.body) {
  return document.body.innerText;
}
return '';
"""
    try:
        result = driver.execute_script(script, selectors, fallback_to_body)
    except WebDriverException:
        return ""

    if not isinstance(result, str):
        return ""
    return result


def extract_title(driver: RemoteWebDriver) -> Optional[str]:
    try:
        title = driver.title
    except WebDriverException:
        title = None
    if title:
        return title.strip()
    return None


def print_to_pdf(driver: RemoteWebDriver, output_path: Path) -> None:
    _prepare_page_for_pdf(driver)
    if hasattr(driver, "save_pdf"):
        driver.save_pdf(
            output_path,
            print_background=True,
            prefer_css_page_size=True,
            scale=0.75,
        )
        return
    data = driver.execute_cdp_cmd(
        "Page.printToPDF",
        {
            "printBackground": True,
            "preferCSSPageSize": True,
            "scale": 0.75,
        },
    )
    pdf_bytes = base64.b64decode(data.get("data", ""))
    output_path.write_bytes(pdf_bytes)


def _prepare_page_for_pdf(driver: RemoteWebDriver, timeout_seconds: float = 20.0) -> None:
    timeout_ms = max(int(timeout_seconds * 1000), 1000)
    script = """
const timeoutMs = Math.max(Number(arguments[0] || 20000), 1000);
const done = arguments[arguments.length - 1];

if (!document.body) {
  done({ total: 0, pending: 0 });
  return;
}

const root =
  document.querySelector("main article") ||
  document.querySelector("article") ||
  document.querySelector("main") ||
  document.body;

const images = Array.from(root.querySelectorAll("img"));
for (const image of images) {
  const dataSrc = image.getAttribute("data-src") || image.dataset?.src || "";
  const dataSrcSet = image.getAttribute("data-srcset") || image.dataset?.srcset || "";

  if (!(image.getAttribute("src") || "").trim() && dataSrc) {
    image.setAttribute("src", dataSrc);
  }
  if (!(image.getAttribute("srcset") || "").trim() && dataSrcSet) {
    image.setAttribute("srcset", dataSrcSet);
  }

  try { image.loading = "eager"; } catch (_) {}
  try { image.decoding = "sync"; } catch (_) {}
  try { image.fetchPriority = "high"; } catch (_) {}
}

const deadline = Date.now() + timeoutMs;

function pendingCount() {
  let pending = 0;
  for (const image of images) {
    const src = image.currentSrc || image.getAttribute("src") || image.getAttribute("data-src") || "";
    if (!src) {
      continue;
    }
    if (!image.complete || !image.naturalWidth) {
      pending += 1;
    }
  }
  return pending;
}

function poll() {
  const pending = pendingCount();
  if (pending === 0 || Date.now() >= deadline) {
    done({ total: images.length, pending });
    return;
  }
  setTimeout(poll, 200);
}

poll();
"""
    try:
        driver.execute_async_script(script, timeout_ms)
    except WebDriverException:
        return


def highlight_keywords_on_page(driver: RemoteWebDriver, keywords: list[str]) -> int:
    cleaned_keywords: list[str] = []
    seen: set[str] = set()
    for keyword in keywords:
        value = " ".join((keyword or "").split())
        if not value:
            continue
        dedup_key = value.casefold()
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        cleaned_keywords.append(value)

    if not cleaned_keywords:
        return 0

    script = """
const keywords = arguments[0] || [];
if (!document.body) {
  return 0;
}

const accentRegex = /[\\u0300-\\u036f]/g;
const normalize = (value) =>
  value.normalize("NFKD").replace(accentRegex, "").toLowerCase();

const normalizedKeywords = Array.from(
  new Set(
    keywords
      .map((keyword) => normalize(String(keyword).trim()).replace(/\\s+/g, " ").trim())
      .filter(Boolean)
  )
).sort((a, b) => b.length - a.length);

if (!normalizedKeywords.length) {
  return 0;
}

const styleId = "luxnews-keyword-highlight-style";
if (!document.getElementById(styleId)) {
  const style = document.createElement("style");
  style.id = styleId;
  style.textContent = "mark[data-luxnews-highlight='1'] { background: #fff176; color: inherit; padding: 0 1px; border-radius: 2px; }";
  document.head.appendChild(style);
}

const skippedTags = new Set(["SCRIPT", "STYLE", "NOSCRIPT", "TEXTAREA", "INPUT", "OPTION", "SELECT"]);
const walker = document.createTreeWalker(
  document.body,
  NodeFilter.SHOW_TEXT,
  {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent) {
        return NodeFilter.FILTER_REJECT;
      }
      if (skippedTags.has(parent.tagName)) {
        return NodeFilter.FILTER_REJECT;
      }
      if (parent.closest("mark[data-luxnews-highlight='1']")) {
        return NodeFilter.FILTER_REJECT;
      }
      if (!node.nodeValue || !node.nodeValue.trim()) {
        return NodeFilter.FILTER_REJECT;
      }
      return NodeFilter.FILTER_ACCEPT;
    },
  }
);

const textNodes = [];
const maxNodes = 6000;
let currentNode;
while ((currentNode = walker.nextNode()) && textNodes.length < maxNodes) {
  textNodes.push(currentNode);
}

const maxHighlights = 1500;
let highlightCount = 0;

function normalizeWithMap(text) {
  let normalized = "";
  const map = [];
  for (let i = 0; i < text.length; i += 1) {
    const normalizedChar = normalize(text[i]);
    for (let j = 0; j < normalizedChar.length; j += 1) {
      normalized += normalizedChar[j];
      map.push(i);
    }
  }
  return { normalized, map };
}

function isWordChar(char) {
  return Boolean(char) && /[\\p{L}\\p{N}]/u.test(char);
}

function hasWordBoundaries(text, start, end) {
  const left = start > 0 ? text[start - 1] : "";
  const right = end < text.length ? text[end] : "";
  return !isWordChar(left) && !isWordChar(right);
}

function collectRanges(text) {
  const { normalized, map } = normalizeWithMap(text);
  if (!normalized) {
    return [];
  }

  const ranges = [];
  for (const keyword of normalizedKeywords) {
    let offset = 0;
    while (offset < normalized.length) {
      const matchIndex = normalized.indexOf(keyword, offset);
      if (matchIndex === -1) {
        break;
      }

      const start = map[matchIndex];
      const end = map[matchIndex + keyword.length - 1] + 1;
      if (start < end && hasWordBoundaries(normalized, matchIndex, matchIndex + keyword.length)) {
        ranges.push([start, end, keyword.length]);
      }

      offset = matchIndex + keyword.length;
      if (ranges.length > 200) {
        break;
      }
    }
  }

  if (!ranges.length) {
    return [];
  }

  ranges.sort((a, b) => (a[0] - b[0]) || (b[2] - a[2]));

  const selected = [];
  let cursor = -1;
  for (const [start, end] of ranges) {
    if (start >= cursor) {
      selected.push([start, end]);
      cursor = end;
    }
  }

  return selected;
}

for (const node of textNodes) {
  if (highlightCount >= maxHighlights) {
    break;
  }

  const text = node.nodeValue || "";
  const ranges = collectRanges(text);
  if (!ranges.length) {
    continue;
  }

  const fragment = document.createDocumentFragment();
  let cursor = 0;
  for (const [start, end] of ranges) {
    if (start > cursor) {
      fragment.appendChild(document.createTextNode(text.slice(cursor, start)));
    }

    const mark = document.createElement("mark");
    mark.setAttribute("data-luxnews-highlight", "1");
    mark.textContent = text.slice(start, end);
    fragment.appendChild(mark);
    cursor = end;
    highlightCount += 1;

    if (highlightCount >= maxHighlights) {
      break;
    }
  }

  if (cursor < text.length) {
    fragment.appendChild(document.createTextNode(text.slice(cursor)));
  }

  if (node.parentNode) {
    node.parentNode.replaceChild(fragment, node);
  }
}

return highlightCount;
"""

    try:
        result = driver.execute_script(script, cleaned_keywords)
    except WebDriverException:
        return 0

    try:
        return int(result or 0)
    except (TypeError, ValueError):
        return 0


def login_wort(
    driver: RemoteWebDriver,
    username: str,
    password: str,
    wait_timeout: float,
    return_to: str = "https://www.wort.lu/",
) -> bool:
    user_value = (username or "").strip()
    password_value = password or ""
    if not user_value or not password_value:
        return False

    if _has_wort_login_cookie(driver):
        return True

    login_url = f"https://www.wort.lu/auth/login?returnTo={quote(return_to, safe='')}"
    try:
        driver.get(login_url)
        wait_for_ready(driver, wait_timeout)
    except WebDriverException as exc:
        LOGGER.warning("Wort login page load failed: %s", exc)
        return False

    username_selectors = [
        (By.ID, "username"),
        (By.NAME, "username"),
        (By.CSS_SELECTOR, "input[type='email']"),
    ]
    password_selectors = [
        (By.ID, "password"),
        (By.NAME, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
    ]

    try:
        username_input = _wait_for_first_displayed(driver, username_selectors, wait_timeout)
        password_input = _wait_for_first_displayed(driver, password_selectors, wait_timeout)
    except TimeoutException:
        # If the login form is not visible but auth cookie exists, session is already ready.
        return _has_wort_login_cookie(driver)

    try:
        username_input.clear()
        username_input.send_keys(user_value)
        password_input.clear()
        password_input.send_keys(password_value)
    except WebDriverException as exc:
        LOGGER.warning("Wort login form fill failed: %s", exc)
        return False

    submit_selectors = [
        (By.CSS_SELECTOR, "button[name='action'][value='default']"),
        (By.CSS_SELECTOR, "button[name='action']"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
    ]
    submit_button = _find_first_displayed(driver, submit_selectors)
    try:
        if submit_button:
            submit_button.click()
        else:
            password_input.send_keys(Keys.ENTER)
    except WebDriverException as exc:
        LOGGER.warning("Wort login submit failed: %s", exc)
        return False

    deadline = time.time() + max(wait_timeout, 5.0)
    while time.time() < deadline:
        if _has_wort_login_cookie(driver):
            return True
        try:
            current_url = (driver.current_url or "").lower()
        except WebDriverException:
            current_url = ""
        if "login.mediahuis.com/u/login" not in current_url and "wort.lu" in current_url:
            if _has_wort_login_cookie(driver):
                return True
        time.sleep(0.35)

    try:
        driver.get(return_to)
        wait_for_ready(driver, wait_timeout)
    except WebDriverException:
        pass

    return _has_wort_login_cookie(driver)


def login_lessentiel(
    driver: RemoteWebDriver,
    email: str,
    password: str,
    wait_timeout: float,
    return_to: str = "https://www.lessentiel.lu/fr",
) -> bool:
    email_value = (email or "").strip()
    password_value = password or ""
    if not email_value or not password_value:
        return False

    try:
        driver.get(return_to)
        wait_for_ready(driver, wait_timeout)
        try_accept_cookies(driver)
    except WebDriverException as exc:
        LOGGER.warning("Lessentiel login start page load failed: %s", exc)
        return False

    if _is_lessentiel_logged_in(driver):
        return True

    login_triggers = [
        (By.XPATH, "//a[normalize-space()='Login']"),
        (By.XPATH, "//a[contains(normalize-space(), 'Connexion')]"),
        (By.XPATH, "//button[normalize-space()='Login']"),
        (By.XPATH, "//button[contains(normalize-space(), 'Connexion')]"),
    ]
    try:
        login_button = _wait_for_first_displayed(driver, login_triggers, wait_timeout)
    except TimeoutException:
        return _is_lessentiel_logged_in(driver)

    try:
        login_button.click()
    except WebDriverException as exc:
        LOGGER.warning("Lessentiel login trigger click failed: %s", exc)
        return False

    # Wait until auth portal opens.
    if not _wait_until_url_contains(driver, "auth.lessentiel.lu", wait_timeout):
        return _is_lessentiel_logged_in(driver)

    # Step 1: email entry.
    email_selectors = [
        (By.CSS_SELECTOR, "input#initial-email"),
        (By.CSS_SELECTOR, "input[type='email']"),
        (By.CSS_SELECTOR, "input[name='email']"),
    ]
    try:
        email_input = _wait_for_first_displayed(driver, email_selectors, wait_timeout)
        email_input.clear()
        email_input.send_keys(email_value)
    except TimeoutException:
        pass
    except WebDriverException as exc:
        LOGGER.warning("Lessentiel email fill failed: %s", exc)
        return False

    # Continue from email step if required.
    _click_auth_button_with_text(
        driver,
        texts=["continuer", "continue", "next"],
    )
    time.sleep(0.6)

    # Some accounts show an intermediate "verify account" step.
    _click_auth_button_with_text(
        driver,
        texts=["verifier le compte", "vérifier le compte", "verify account"],
    )
    time.sleep(0.6)

    # The current auth flow may require email OTP verification before password.
    if _is_lessentiel_code_verification_step(driver):
        LOGGER.warning("Lessentiel login requires email code verification.")
        return False

    password_selectors = [
        (By.CSS_SELECTOR, "input[type='password']"),
        (By.CSS_SELECTOR, "input[name='password']"),
    ]
    try:
        password_input = _wait_for_first_displayed(driver, password_selectors, wait_timeout)
    except TimeoutException:
        # If password input does not appear, session may already be accepted and redirected.
        if _is_lessentiel_code_verification_step(driver):
            LOGGER.warning("Lessentiel login paused on email code verification step.")
            return False
        try:
            driver.get(return_to)
            wait_for_ready(driver, wait_timeout)
            try_accept_cookies(driver)
        except WebDriverException:
            return False
        return _is_lessentiel_logged_in(driver)

    try:
        password_input.clear()
        password_input.send_keys(password_value)
    except WebDriverException as exc:
        LOGGER.warning("Lessentiel password fill failed: %s", exc)
        return False

    submitted = _click_auth_button_with_text(
        driver,
        texts=[
            "se connecter",
            "connexion",
            "connect",
            "login",
            "sign in",
            "anmelden",
        ],
    )
    if not submitted:
        try:
            password_input.send_keys(Keys.ENTER)
        except WebDriverException:
            return False

    deadline = time.time() + max(wait_timeout, 8.0)
    while time.time() < deadline:
        try:
            current_url = (driver.current_url or "").lower()
        except WebDriverException:
            current_url = ""
        if "auth.lessentiel.lu" not in current_url and "lessentiel.lu" in current_url:
            break
        time.sleep(0.35)

    try:
        driver.get(return_to)
        wait_for_ready(driver, wait_timeout)
        try_accept_cookies(driver)
    except WebDriverException:
        return False

    return _is_lessentiel_logged_in(driver)


def _has_wort_login_cookie(driver: RemoteWebDriver) -> bool:
    try:
        cookie = driver.get_cookie(WORT_ID_TOKEN_COOKIE)
    except WebDriverException:
        return False
    return bool(cookie and cookie.get("value"))


def login_contacto(
    driver: RemoteWebDriver,
    email: str,
    password: str,
    wait_timeout: float,
    return_to: str = "https://www.contacto.lu/",
) -> bool:
    email_value = (email or "").strip()
    password_value = password or ""
    if not email_value or not password_value:
        return False

    if _has_contacto_login_cookie(driver):
        return True

    login_url = f"https://www.contacto.lu/auth/login?returnTo={quote(return_to, safe='')}"
    try:
        driver.get(login_url)
        wait_for_ready(driver, wait_timeout)
    except WebDriverException as exc:
        LOGGER.warning("Contacto login page load failed: %s", exc)
        return False

    username_selectors = [
        (By.ID, "username"),
        (By.NAME, "username"),
        (By.CSS_SELECTOR, "input[type='email']"),
    ]
    password_selectors = [
        (By.ID, "password"),
        (By.NAME, "password"),
        (By.CSS_SELECTOR, "input[type='password']"),
    ]

    try:
        username_input = _wait_for_first_displayed(driver, username_selectors, wait_timeout)
        password_input = _wait_for_first_displayed(driver, password_selectors, wait_timeout)
    except TimeoutException:
        return _has_contacto_login_cookie(driver)

    try:
        username_input.clear()
        username_input.send_keys(email_value)
        password_input.clear()
        password_input.send_keys(password_value)
    except WebDriverException as exc:
        LOGGER.warning("Contacto login form fill failed: %s", exc)
        return False

    submit_selectors = [
        (By.CSS_SELECTOR, "button[name='action'][value='default']"),
        (By.CSS_SELECTOR, "button[name='action']"),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
    ]
    submit_button = _find_first_displayed(driver, submit_selectors)
    try:
        if submit_button:
            submit_button.click()
        else:
            password_input.send_keys(Keys.ENTER)
    except WebDriverException as exc:
        LOGGER.warning("Contacto login submit failed: %s", exc)
        return False

    deadline = time.time() + max(wait_timeout, 5.0)
    while time.time() < deadline:
        if _has_contacto_login_cookie(driver):
            return True
        try:
            current_url = (driver.current_url or "").lower()
        except WebDriverException:
            current_url = ""
        if "login.mediahuis.com" not in current_url and "contacto.lu" in current_url:
            if _has_contacto_login_cookie(driver):
                return True
        time.sleep(0.35)

    try:
        driver.get(return_to)
        wait_for_ready(driver, wait_timeout)
    except WebDriverException:
        pass

    return _has_contacto_login_cookie(driver)


def _has_contacto_login_cookie(driver: RemoteWebDriver) -> bool:
    try:
        cookie = driver.get_cookie(CONTACTO_ID_TOKEN_COOKIE)
    except WebDriverException:
        return False
    return bool(cookie and cookie.get("value"))


def _wait_for_first_displayed(
    driver: RemoteWebDriver,
    selectors: list[tuple[str, str]],
    timeout: float,
):
    return WebDriverWait(driver, timeout).until(
        lambda d: _find_first_displayed(d, selectors)
    )


def _find_first_displayed(driver: RemoteWebDriver, selectors: list[tuple[str, str]]):
    for by, value in selectors:
        try:
            elements = driver.find_elements(by, value)
        except WebDriverException:
            continue
        for element in elements:
            try:
                if element.is_displayed():
                    return element
            except WebDriverException:
                continue
    return None


def _wait_until_url_contains(driver: RemoteWebDriver, fragment: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    expected = (fragment or "").lower()
    while time.time() < deadline:
        try:
            current = (driver.current_url or "").lower()
        except WebDriverException:
            current = ""
        if expected and expected in current:
            return True
        time.sleep(0.2)
    return False


def _click_auth_button_with_text(driver: RemoteWebDriver, texts: list[str]) -> bool:
    wanted = [value.casefold() for value in texts if value]
    if not wanted:
        return False

    for button in driver.find_elements(By.CSS_SELECTOR, "button, [role='button']"):
        try:
            if not button.is_displayed():
                continue
            text = " ".join((button.text or "").split()).casefold()
            if not text:
                continue
            if any(token in text for token in wanted):
                button.click()
                return True
        except WebDriverException:
            continue
    return False


def _is_lessentiel_logged_in(driver: RemoteWebDriver) -> bool:
    script = """
function isVisible(el) {
  if (!el) return false;
  const style = window.getComputedStyle(el);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
    return false;
  }
  const rect = el.getBoundingClientRect();
  return rect.width > 0 && rect.height > 0;
}
const selectors = ['a', 'button', '[role=\"button\"]'];
const labels = ['login', 'connexion', 'se connecter'];
for (const selector of selectors) {
  const nodes = Array.from(document.querySelectorAll(selector));
  for (const node of nodes) {
    if (!isVisible(node)) continue;
    const text = (node.innerText || node.textContent || '').toLowerCase().replace(/\\s+/g, ' ').trim();
    if (!text) continue;
    if (labels.includes(text)) {
      return false;
    }
  }
}
return true;
"""
    try:
        result = driver.execute_script(script)
    except WebDriverException:
        return False
    return bool(result)


def _is_lessentiel_code_verification_step(driver: RemoteWebDriver) -> bool:
    script = """
const bodyText = (document.body ? document.body.innerText : '')
  .toLowerCase()
  .replace(/\\s+/g, ' ');
if (bodyText.includes(\"confirmer l'e-mail\") || bodyText.includes('confirmer l’e-mail')) {
  return true;
}
if (bodyText.includes('email avec code') || bodyText.includes('code envoyé')) {
  return true;
}
const codeInputs = document.querySelectorAll(
  \"input[name*='code'], input[id*='code'], input[autocomplete='one-time-code']\"
);
return codeInputs.length > 0;
"""
    try:
        result = driver.execute_script(script)
    except WebDriverException:
        return False
    return bool(result)


def try_accept_cookies(driver: RemoteWebDriver) -> None:
    try:
        _click_known_cookie_accept_buttons(driver)

        # Some CMP popups appear with a delay after initial load.
        for _ in range(3):
            if not _is_didomi_overlay_visible(driver):
                break
            if _click_didomi_accept(driver):
                time.sleep(0.4)
                continue
            break

        if _is_didomi_overlay_visible(driver):
            _hide_didomi_overlay(driver)
    except WebDriverException:
        return


def _click_known_cookie_accept_buttons(driver: RemoteWebDriver) -> bool:
    selectors = [
        "#didomi-notice-agree-button",
        "#btn-toggle-agree",
        "#onetrust-accept-btn-handler",
        "button[id*='cookie'][id*='accept']",
        "button[class*='cookie'][class*='accept']",
        "button[id*='consent'][id*='accept']",
        "button[class*='consent'][class*='accept']",
    ]
    for selector in selectors:
        if _click_first_displayed(driver, By.CSS_SELECTOR, selector):
            time.sleep(0.3)
            return True
    return False


def _click_didomi_accept(driver: RemoteWebDriver) -> bool:
    selectors = [
        "#btn-toggle-agree",
        "#didomi-notice-agree-button",
        "#didomi-host #btn-toggle-agree",
        "#didomi-consent-popup #btn-toggle-agree",
    ]
    for selector in selectors:
        if _click_first_displayed(driver, By.CSS_SELECTOR, selector):
            return True

    # Fallback for localized Didomi labels inside the popup.
    script = """
function isVisible(el) {
  if (!el) return false;
  const style = window.getComputedStyle(el);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
    return false;
  }
  const rect = el.getBoundingClientRect();
  return rect.width > 4 && rect.height > 4;
}
function norm(value) {
  return (value || '').toLowerCase().replace(/\\s+/g, ' ').trim();
}
const roots = Array.from(document.querySelectorAll(
  '#didomi-consent-popup, #didomi-host, .didomi-popup-open, .didomi-popup-container'
)).filter(isVisible);
if (!roots.length) {
  return false;
}
const preferredLabels = [
  'alle annehmen',
  'all accept',
  'accept all',
  'allow all',
  'tout accepter',
  'alle akzeptieren',
  'alles akzeptieren',
  'accepter tout',
  \"j'accepte\"
];
const negativeLabels = ['ablehnen', 'reject', 'decline', 'disagree', 'deny', 'refuse'];
for (const root of roots) {
  const buttons = Array.from(root.querySelectorAll('button, a, [role=\"button\"]'));
  for (const button of buttons) {
    if (!isVisible(button)) continue;
    const text = norm(button.innerText || button.textContent || '');
    if (!text || negativeLabels.some((label) => text.includes(label))) {
      continue;
    }
    if (preferredLabels.some((label) => text.includes(label))) {
      button.click();
      return true;
    }
  }
}
return false;
"""
    try:
        result = driver.execute_script(script)
        return bool(result)
    except WebDriverException:
        return False


def _is_didomi_overlay_visible(driver: RemoteWebDriver) -> bool:
    script = """
function isVisible(el) {
  if (!el) return false;
  const style = window.getComputedStyle(el);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
    return false;
  }
  const rect = el.getBoundingClientRect();
  return rect.width > 20 && rect.height > 20;
}
const selectors = [
  '#didomi-consent-popup',
  '.didomi-popup-open',
  '.didomi-popup-container',
  '.didomi-popup-backdrop'
];
for (const selector of selectors) {
  const nodes = document.querySelectorAll(selector);
  for (const node of nodes) {
    if (isVisible(node)) {
      return true;
    }
  }
}
return false;
"""
    try:
        return bool(driver.execute_script(script))
    except WebDriverException:
        return False


def _hide_didomi_overlay(driver: RemoteWebDriver) -> None:
    script = """
const selectors = [
  '#didomi-consent-popup',
  '.didomi-popup-open',
  '.didomi-popup-container',
  '.didomi-popup-backdrop',
  '#didomi-host'
];
for (const selector of selectors) {
  const nodes = Array.from(document.querySelectorAll(selector));
  for (const node of nodes) {
    node.remove();
  }
}
document.documentElement.classList.remove('didomi-popup-open');
document.body.classList.remove('didomi-popup-open');
document.body.style.overflow = '';
"""
    try:
        driver.execute_script(script)
    except WebDriverException:
        return


def _click_first_displayed(driver: RemoteWebDriver, by: str, value: str) -> bool:
    try:
        elements = driver.find_elements(by, value)
    except WebDriverException:
        return False

    for element in elements:
        try:
            if not element.is_displayed():
                continue
        except WebDriverException:
            continue
        try:
            element.click()
            return True
        except WebDriverException:
            try:
                driver.execute_script("arguments[0].click();", element)
                return True
            except WebDriverException:
                continue
    return False


def capture_screenshot(driver: RemoteWebDriver, output_path: Path) -> None:
    try:
        driver.save_screenshot(str(output_path))
    except WebDriverException as exc:
        LOGGER.debug("Screenshot failed: %s", exc)


def capture_mhtml(driver: RemoteWebDriver, output_path: Path) -> None:
    if hasattr(driver, "capture_mhtml"):
        try:
            driver.capture_mhtml(output_path)
        except WebDriverException as exc:
            LOGGER.debug("MHTML capture failed: %s", exc)
        return
    try:
        result = driver.execute_cdp_cmd("Page.captureSnapshot", {"format": "mhtml"})
        data = result.get("data")
        if data:
            output_path.write_text(data, encoding="utf-8")
    except WebDriverException as exc:
        LOGGER.debug("MHTML capture failed: %s", exc)


def get_logs(driver: RemoteWebDriver, log_type: str) -> list[dict]:
    try:
        return driver.get_log(log_type)
    except WebDriverException:
        return []
