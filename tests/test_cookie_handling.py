import pytest

try:
    from luxnews.browser_types import By
    import luxnews.browser_utils as browser_utils
except ModuleNotFoundError:
    By = None
    browser_utils = None


class _DummyElement:
    def __init__(self, displayed: bool = True):
        self.displayed = displayed
        self.clicked = False

    def is_displayed(self):
        return self.displayed

    def click(self):
        self.clicked = True


class _DummyDriver:
    def __init__(self, *, css_elements=None, script_returns=None):
        self.css_elements = css_elements or {}
        self.script_returns = list(script_returns or [])
        self.find_calls: list[tuple[str, str]] = []
        self.script_calls: list[str] = []

    def find_elements(self, by, value):
        self.find_calls.append((by, value))
        if by == By.TAG_NAME:
            raise AssertionError("try_accept_cookies should not scan all page buttons")
        if by == By.CSS_SELECTOR:
            return self.css_elements.get(value, [])
        return []

    def execute_script(self, script, *args):
        self.script_calls.append(script)
        if self.script_returns:
            return self.script_returns.pop(0)
        return None


@pytest.mark.skipif(browser_utils is None, reason="browser helpers not available")
def test_try_accept_cookies_clicks_known_accept_selector(monkeypatch):
    monkeypatch.setattr(browser_utils.time, "sleep", lambda *_: None)
    button = _DummyElement()
    driver = _DummyDriver(
        css_elements={"#btn-toggle-agree": [button]},
        script_returns=[False, False],
    )

    browser_utils.try_accept_cookies(driver)

    assert button.clicked is True


@pytest.mark.skipif(browser_utils is None, reason="browser helpers not available")
def test_try_accept_cookies_does_not_click_random_buttons(monkeypatch):
    monkeypatch.setattr(browser_utils.time, "sleep", lambda *_: None)
    driver = _DummyDriver(script_returns=[False, False])

    browser_utils.try_accept_cookies(driver)

    assert all(by != By.TAG_NAME for by, _ in driver.find_calls)


@pytest.mark.skipif(browser_utils is None, reason="browser helpers not available")
def test_try_accept_cookies_hides_didomi_overlay_when_still_visible(monkeypatch):
    monkeypatch.setattr(browser_utils.time, "sleep", lambda *_: None)
    driver = _DummyDriver(script_returns=[True, False, True, None])

    browser_utils.try_accept_cookies(driver)

    assert any("node.remove();" in script for script in driver.script_calls)
