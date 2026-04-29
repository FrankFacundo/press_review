from __future__ import annotations


class BrowserError(Exception):
    """Browser automation error raised by LuxNews' Playwright adapter."""


class BrowserTimeoutError(BrowserError):
    """Browser operation timed out."""


class By:
    CSS_SELECTOR = "css selector"
    ID = "id"
    NAME = "name"
    TAG_NAME = "tag name"
    XPATH = "xpath"


class Keys:
    BACKSPACE = "\ue003"
    ENTER = "\ue007"
    CONTROL = "\ue009"
    META = "\ue03d"
    COMMAND = META
