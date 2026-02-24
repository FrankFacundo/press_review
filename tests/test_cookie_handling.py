import pytest

try:
    from selenium.webdriver.common.by import By
    import luxnews.selenium_utils as selenium_utils
except ModuleNotFoundError:
    By = None
    selenium_utils = None


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


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_try_accept_cookies_clicks_known_accept_selector(monkeypatch):
    monkeypatch.setattr(selenium_utils.time, "sleep", lambda *_: None)
    button = _DummyElement()
    driver = _DummyDriver(
        css_elements={"#btn-toggle-agree": [button]},
        script_returns=[False, False],
    )

    selenium_utils.try_accept_cookies(driver)

    assert button.clicked is True


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_try_accept_cookies_does_not_click_random_buttons(monkeypatch):
    monkeypatch.setattr(selenium_utils.time, "sleep", lambda *_: None)
    driver = _DummyDriver(script_returns=[False, False])

    selenium_utils.try_accept_cookies(driver)

    assert all(by != By.TAG_NAME for by, _ in driver.find_calls)


@pytest.mark.skipif(selenium_utils is None, reason="selenium not installed")
def test_try_accept_cookies_hides_didomi_overlay_when_still_visible(monkeypatch):
    monkeypatch.setattr(selenium_utils.time, "sleep", lambda *_: None)
    driver = _DummyDriver(script_returns=[True, False, True, None])

    selenium_utils.try_accept_cookies(driver)

    assert any("node.remove();" in script for script in driver.script_calls)
