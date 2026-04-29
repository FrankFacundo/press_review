from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote

from luxnews.browser_types import By, Keys, BrowserTimeoutError, BrowserError

LOGGER = logging.getLogger(__name__)
WORT_AUTH0_CLIENT_ID = "92cIfq2nCGyCc7meGRMjCJ7T8IBlIxIq"
WORT_ID_TOKEN_COOKIE = f"auth0_{WORT_AUTH0_CLIENT_ID}_id_token"
CONTACTO_AUTH0_CLIENT_ID = "H8NL70vxzZhzeWkgNOfPchPA8wsPayIZ"
CONTACTO_ID_TOKEN_COOKIE = f"auth0_{CONTACTO_AUTH0_CLIENT_ID}_id_token"
_ACTIVE_DRIVER_LOCK = threading.Lock()
_ACTIVE_DRIVER = None
BrowserDriver = Any


def create_driver(
    driver_name: str,
    headless: bool,
    open_devtools: bool,
    enable_logging: bool,
    page_timeout: float,
) -> BrowserDriver:
    driver_name = (driver_name or "").strip().lower()
    if driver_name != "playwright":
        raise ValueError("driver must be 'playwright'")

    from luxnews.playwright_utils import create_playwright_driver

    driver = create_playwright_driver(
        headless=headless,
        open_devtools=open_devtools,
        enable_logging=enable_logging,
        page_timeout=page_timeout,
    )
    return _track_driver(driver)


def close_active_driver() -> bool:
    global _ACTIVE_DRIVER
    with _ACTIVE_DRIVER_LOCK:
        driver = _ACTIVE_DRIVER
        _ACTIVE_DRIVER = None
    if driver is None:
        return False
    try:
        driver.quit()
    except Exception:  # noqa: BLE001
        LOGGER.debug("Active driver shutdown raised an error.", exc_info=True)
    return True


def _track_driver(driver):
    global _ACTIVE_DRIVER

    if getattr(driver, "_luxnews_tracked_driver", False):
        with _ACTIVE_DRIVER_LOCK:
            _ACTIVE_DRIVER = driver
        return driver

    original_quit = driver.quit

    def tracked_quit(*args, **kwargs):
        global _ACTIVE_DRIVER
        with _ACTIVE_DRIVER_LOCK:
            if _ACTIVE_DRIVER is driver:
                _ACTIVE_DRIVER = None
        return original_quit(*args, **kwargs)

    driver.quit = tracked_quit
    driver._luxnews_tracked_driver = True
    with _ACTIVE_DRIVER_LOCK:
        _ACTIVE_DRIVER = driver
    return driver


def wait_for_ready(driver: BrowserDriver, wait_timeout: float) -> None:
    deadline = time.time() + max(wait_timeout, 0.1)
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                return
        except BrowserError as exc:
            last_error = exc
        time.sleep(0.1)
    if last_error:
        raise BrowserTimeoutError(str(last_error))
    raise BrowserTimeoutError("Timed out waiting for document.readyState == 'complete'")


def extract_visible_text(driver: BrowserDriver) -> str:
    try:
        return driver.execute_script("return document.body ? document.body.innerText : ''")
    except BrowserError:
        return ""


def extract_visible_text_from_selectors(
    driver: BrowserDriver,
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
    except BrowserError:
        return ""

    if not isinstance(result, str):
        return ""
    return result


def extract_title(driver: BrowserDriver) -> Optional[str]:
    try:
        title = driver.title
    except BrowserError:
        title = None
    if title:
        return title.strip()
    return None


_PDF_LAYOUT_STYLE_ID = "luxnews-pdf-layout-style"


def reserve_space_for_pdf_header(driver: BrowserDriver) -> None:
    """Apply shared article layout tweaks before printing to PDF.

    - CSS ``@page`` top margin so the stamp drawn by
      ``stamp_article_pdf_header`` (text at ~14pt, line at ~22pt from the
      page top) does not overlap article content on any page — not just
      the first one.
    - Width cap (~3/4 of the print page) with auto margins so full-width
      media sites don't render edge-to-edge in the PDF.
    """
    script = """
var STYLE_ID = arguments[0];
var existing = document.getElementById(STYLE_ID);
if (!existing) {
  var style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = (
    "@page { margin: 0.6in 0.3in 0.4in 0.3in; } " +
    "html, body { overflow-x: hidden !important; } " +
    "body { " +
    "  max-width: 1400px !important; " +
    "  margin-left: auto !important; " +
    "  margin-right: auto !important; " +
    "  padding-left: 24px !important; " +
    "  padding-right: 24px !important; " +
    "  box-sizing: border-box !important; " +
    "}"
  );
  (document.head || document.documentElement).appendChild(style);
}
"""
    try:
        driver.execute_script(script, _PDF_LAYOUT_STYLE_ID)
    except (BrowserError, AttributeError):
        return


def print_to_pdf(driver: BrowserDriver, output_path: Path) -> None:
    _prepare_page_for_pdf(driver)
    if hasattr(driver, "save_pdf"):
        driver.save_pdf(
            output_path,
            print_background=True,
            prefer_css_page_size=True,
            scale=0.75,
        )
        return
    raise BrowserError("Active browser driver does not support PDF export.")


def _prepare_page_for_pdf(driver: BrowserDriver, timeout_seconds: float = 20.0) -> None:
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
    except BrowserError:
        return


def highlight_keywords_on_page(driver: BrowserDriver, keywords: list[str]) -> int:
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
let style = document.getElementById(styleId);
if (!style) {
  style = document.createElement("style");
  style.id = styleId;
  document.head.appendChild(style);
}
style.textContent = `
  mark[data-luxnews-highlight='1'] {
    background: #fff176 !important;
    background-color: #fff176 !important;
    color: #000 !important;
    padding: 0 1px;
    border-radius: 2px;
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
  }
`;

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
    except BrowserError:
        return 0

    try:
        return int(result or 0)
    except (TypeError, ValueError):
        return 0


def login_wort(
    driver: BrowserDriver,
    username: str,
    password: str,
    wait_timeout: float,
    return_to: str = "https://www.wort.lu/",
) -> bool:
    return _login_mediahuis_site(
        driver=driver,
        username=username,
        password=password,
        wait_timeout=wait_timeout,
        return_to=return_to,
        login_origin="https://www.wort.lu",
        expected_domain="wort.lu",
        site_name="Wort",
    )


def login_luxtimes(
    driver: BrowserDriver,
    username: str,
    password: str,
    wait_timeout: float,
    return_to: str = "https://www.luxtimes.lu/",
) -> bool:
    return _login_mediahuis_site(
        driver=driver,
        username=username,
        password=password,
        wait_timeout=wait_timeout,
        return_to=return_to,
        login_origin="https://www.luxtimes.lu",
        expected_domain="luxtimes.lu",
        site_name="LuxTimes",
    )


def _login_mediahuis_site(
    driver: BrowserDriver,
    username: str,
    password: str,
    wait_timeout: float,
    return_to: str,
    login_origin: str,
    expected_domain: str,
    site_name: str,
) -> bool:
    user_value = (username or "").strip()
    password_value = password or ""
    if not user_value or not password_value:
        return False

    if _current_url_contains(driver, expected_domain) and _has_mediahuis_login_cookie(driver):
        return True

    login_url = f"{login_origin.rstrip('/')}/auth/login?returnTo={quote(return_to, safe='')}"
    try:
        driver.get(login_url)
        wait_for_ready(driver, wait_timeout)
    except BrowserError as exc:
        LOGGER.warning("%s login page load failed: %s", site_name, exc)
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
    except BrowserTimeoutError:
        # If the login form is not visible but auth cookie exists, session is already ready.
        return _has_mediahuis_login_cookie(driver)

    try:
        username_input.clear()
        username_input.send_keys(user_value)
        password_input.clear()
        password_input.send_keys(password_value)
    except BrowserError as exc:
        LOGGER.warning("%s login form fill failed: %s", site_name, exc)
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
    except BrowserError as exc:
        LOGGER.warning("%s login submit failed: %s", site_name, exc)
        return False

    deadline = time.time() + max(wait_timeout, 5.0)
    while time.time() < deadline:
        if _has_mediahuis_login_cookie(driver):
            return True
        try:
            current_url = (driver.current_url or "").lower()
        except BrowserError:
            current_url = ""
        if "login.mediahuis.com" not in current_url and expected_domain in current_url:
            if _has_mediahuis_login_cookie(driver):
                return True
        time.sleep(0.35)

    try:
        driver.get(return_to)
        wait_for_ready(driver, wait_timeout)
    except BrowserError:
        pass

    return _has_mediahuis_login_cookie(driver)


def login_lessentiel(
    driver: BrowserDriver,
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
    except BrowserError as exc:
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
    except BrowserTimeoutError:
        return _is_lessentiel_logged_in(driver)

    try:
        login_button.click()
    except BrowserError as exc:
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
    except BrowserTimeoutError:
        pass
    except BrowserError as exc:
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
    except BrowserTimeoutError:
        # If password input does not appear, session may already be accepted and redirected.
        if _is_lessentiel_code_verification_step(driver):
            LOGGER.warning("Lessentiel login paused on email code verification step.")
            return False
        try:
            driver.get(return_to)
            wait_for_ready(driver, wait_timeout)
            try_accept_cookies(driver)
        except BrowserError:
            return False
        return _is_lessentiel_logged_in(driver)

    try:
        password_input.clear()
        password_input.send_keys(password_value)
    except BrowserError as exc:
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
        except BrowserError:
            return False

    deadline = time.time() + max(wait_timeout, 8.0)
    while time.time() < deadline:
        try:
            current_url = (driver.current_url or "").lower()
        except BrowserError:
            current_url = ""
        if "auth.lessentiel.lu" not in current_url and "lessentiel.lu" in current_url:
            break
        time.sleep(0.35)

    try:
        driver.get(return_to)
        wait_for_ready(driver, wait_timeout)
        try_accept_cookies(driver)
    except BrowserError:
        return False

    return _is_lessentiel_logged_in(driver)


def _has_mediahuis_login_cookie(driver: BrowserDriver) -> bool:
    # Mediahuis rotates the Auth0 client id underpinning the cookie name
    # (`auth0_<client_id>_id_token`), so match any current id-token cookie
    # rather than the historical literal in WORT_ID_TOKEN_COOKIE.
    try:
        cookie = driver.get_cookie(WORT_ID_TOKEN_COOKIE)
    except BrowserError:
        cookie = None
    if cookie and cookie.get("value"):
        return True

    try:
        cookies = driver.get_cookies() or []
    except BrowserError:
        return False
    for entry in cookies:
        name = entry.get("name") or ""
        if name.startswith("auth0_") and name.endswith("_id_token") and entry.get("value"):
            return True
    return False


def _has_wort_login_cookie(driver: BrowserDriver) -> bool:
    return _has_mediahuis_login_cookie(driver)


def _current_url_contains(driver: BrowserDriver, value: str) -> bool:
    try:
        current_url = (driver.current_url or "").lower()
    except BrowserError:
        return False
    return bool(value and value.lower() in current_url)


def login_contacto(
    driver: BrowserDriver,
    email: str,
    password: str,
    wait_timeout: float,
    return_to: str = "https://www.contacto.lu/",
) -> bool:
    email_value = (email or "").strip()
    password_value = password or ""
    if not email_value or not password_value:
        return False

    if _current_url_contains(driver, "contacto.lu") and _has_contacto_login_cookie(driver):
        return True

    login_url = f"https://www.contacto.lu/auth/login?returnTo={quote(return_to, safe='')}"
    try:
        driver.get(login_url)
        wait_for_ready(driver, wait_timeout)
    except BrowserError as exc:
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
    except BrowserTimeoutError:
        return _has_contacto_login_cookie(driver)

    try:
        username_input.clear()
        username_input.send_keys(email_value)
        password_input.clear()
        password_input.send_keys(password_value)
    except BrowserError as exc:
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
    except BrowserError as exc:
        LOGGER.warning("Contacto login submit failed: %s", exc)
        return False

    deadline = time.time() + max(wait_timeout, 5.0)
    while time.time() < deadline:
        if _has_contacto_login_cookie(driver):
            return True
        try:
            current_url = (driver.current_url or "").lower()
        except BrowserError:
            current_url = ""
        if "login.mediahuis.com" not in current_url and "contacto.lu" in current_url:
            if _has_contacto_login_cookie(driver):
                return True
        time.sleep(0.35)

    try:
        driver.get(return_to)
        wait_for_ready(driver, wait_timeout)
    except BrowserError:
        pass

    return _has_contacto_login_cookie(driver)


def _has_contacto_login_cookie(driver: BrowserDriver) -> bool:
    try:
        cookie = driver.get_cookie(CONTACTO_ID_TOKEN_COOKIE)
    except BrowserError:
        cookie = None
    if cookie and cookie.get("value"):
        return True

    try:
        cookies = driver.get_cookies() or []
    except BrowserError:
        return False
    for entry in cookies:
        name = entry.get("name") or ""
        if name.startswith("auth0_") and name.endswith("_id_token") and entry.get("value"):
            return True
    return False


def _wait_for_first_displayed(
    driver: BrowserDriver,
    selectors: list[tuple[str, str]],
    timeout: float,
):
    deadline = time.time() + max(timeout, 0.1)
    while time.time() < deadline:
        element = _find_first_displayed(driver, selectors)
        if element:
            return element
        time.sleep(0.2)
    raise BrowserTimeoutError("Timed out waiting for a displayed element.")


def _find_first_displayed(driver: BrowserDriver, selectors: list[tuple[str, str]]):
    for by, value in selectors:
        try:
            elements = driver.find_elements(by, value)
        except BrowserError:
            continue
        for element in elements:
            try:
                if element.is_displayed():
                    return element
            except BrowserError:
                continue
    return None


def _wait_until_url_contains(driver: BrowserDriver, fragment: str, timeout: float) -> bool:
    deadline = time.time() + timeout
    expected = (fragment or "").lower()
    while time.time() < deadline:
        try:
            current = (driver.current_url or "").lower()
        except BrowserError:
            current = ""
        if expected and expected in current:
            return True
        time.sleep(0.2)
    return False


def _click_auth_button_with_text(driver: BrowserDriver, texts: list[str]) -> bool:
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
        except BrowserError:
            continue
    return False


def _is_lessentiel_logged_in(driver: BrowserDriver) -> bool:
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
    except BrowserError:
        return False
    return bool(result)


def _is_lessentiel_code_verification_step(driver: BrowserDriver) -> bool:
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
    except BrowserError:
        return False
    return bool(result)


def try_accept_cookies(driver: BrowserDriver) -> None:
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
    except BrowserError:
        return


def _click_known_cookie_accept_buttons(driver: BrowserDriver) -> bool:
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


def _click_didomi_accept(driver: BrowserDriver) -> bool:
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
    except BrowserError:
        return False


def _is_didomi_overlay_visible(driver: BrowserDriver) -> bool:
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
    except BrowserError:
        return False


def _hide_didomi_overlay(driver: BrowserDriver) -> None:
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
    except BrowserError:
        return


def _click_first_displayed(driver: BrowserDriver, by: str, value: str) -> bool:
    try:
        elements = driver.find_elements(by, value)
    except BrowserError:
        return False

    for element in elements:
        try:
            if not element.is_displayed():
                continue
        except BrowserError:
            continue
        try:
            element.click()
            return True
        except BrowserError:
            try:
                driver.execute_script("arguments[0].click();", element)
                return True
            except BrowserError:
                continue
    return False


def capture_screenshot(driver: BrowserDriver, output_path: Path) -> None:
    try:
        driver.save_screenshot(str(output_path))
    except BrowserError as exc:
        LOGGER.debug("Screenshot failed: %s", exc)


def capture_mhtml(driver: BrowserDriver, output_path: Path) -> None:
    if hasattr(driver, "capture_mhtml"):
        try:
            driver.capture_mhtml(output_path)
        except BrowserError as exc:
            LOGGER.debug("MHTML capture failed: %s", exc)
        return
    LOGGER.debug("MHTML capture skipped: active browser driver does not support it.")


def get_logs(driver: BrowserDriver, log_type: str) -> list[dict]:
    try:
        return driver.get_log(log_type)
    except BrowserError:
        return []
